"""ROI analysis module for behavioral studies.

This module defines the ROIAnalyzer class for detailed behavioral analysis
within specific regions of interest (ROIs).
"""

from itertools import combinations
from typing import Any, Literal

import networkx as nx
import numpy as np
import pandas as pd
import shapely
from shapely import affinity, prepare
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from zebtrack.analysis.behavior import BehavioralAnalyzer
from zebtrack.core.services.roi_rule_resolver import (
    DEFAULT_BBOX_OVERLAP_BASIS,
    DEFAULT_BUFFER_RADIUS_VALUE,
    DEFAULT_MIN_BBOX_OVERLAP_RATIO,
    DEFAULT_ROI_FLUTTER_ENTER_FRAMES,
    DEFAULT_ROI_FLUTTER_EXIT_FRAMES,
    DEFAULT_ROI_INCLUSION_RULE,
    DEFAULT_ROI_MAX_GAP_S,
    DEFAULT_ROI_MIN_GAP_S,
    DEFAULT_ROI_MIN_VISIT_S,
    MAX_GAP_AUTO_FACTOR,
    VALID_ROI_INCLUSION_RULES,
    RoiRuleConfig,
)

# Padrão DE-9IM "interiores se tocam": é o predicado de sobreposição de área
# NÃO-NULA. `intersects` não serve — devolve True para tangência (contato só de
# borda), que não é sobreposição. Comparar área > 0 também não: em quase
# tangência a área é positiva por ruído de ponto flutuante, enquanto o
# predicado topológico decide pela relação, não pela magnitude.
_INTERIORS_INTERSECT: str = "T********"


def _first_not_none(*candidates: Any) -> Any:
    """Primeiro candidato não-``None``.

    Existe para não escrever ``a or b``: os valores em jogo aqui incluem ``0``
    e ``0.0`` legítimos ("desligado"), e ``0 or 3`` é ``3``.
    """
    for candidate in candidates:
        if candidate is not None:
            return candidate
    return None


def _assign_stable_roi(frame: pd.DataFrame, roi_names: Any) -> None:
    """Escreve a coluna ``stable_roi`` (nome da ROI atual, ou ``"Outside"``)."""
    frame["stable_roi"] = "Outside"
    for name in roi_names:
        frame.loc[frame[f"in_{name}_stable"], "stable_roi"] = name


def _to_seconds(value: Any) -> float:
    """``Timedelta`` (ou número) para segundos."""
    return value.total_seconds() if hasattr(value, "total_seconds") else float(value)


# As quatro métricas abaixo são funções livres, não métodos, porque rodam sobre
# DOIS quadros diferentes: a linha do tempo de grupo (``_view``) para os números
# publicados e o recorte de UM animal para os números por sujeito. Como método
# elas leriam ``self._trajectory`` e não haveria como pedir o recorte.
def _time_spent_in_rois(frame: pd.DataFrame, roi_names: Any) -> dict[str, dict[str, float]]:
    """Tempo total (segundos e percentual) em cada ROI, para o quadro dado."""
    results = {}
    total_time = frame["dt"].sum()
    if total_time == 0:
        return {name: {"seconds": 0.0, "percentage": 0.0} for name in roi_names}

    total_time_seconds = _to_seconds(total_time)

    for name in roi_names:
        time_in_roi = frame.loc[frame[f"in_{name}_stable"], "dt"].sum()
        time_in_roi_seconds = _to_seconds(time_in_roi)
        results[name] = {
            "seconds": time_in_roi_seconds,
            "percentage": (time_in_roi_seconds / total_time_seconds) * 100
            if total_time_seconds > 0
            else 0.0,
        }
    return results


def _latency_to_first_entry(frame: pd.DataFrame, roi_names: Any) -> dict[str, float | None]:
    """Latência até a primeira entrada em cada ROI, para o quadro dado."""
    results: dict[str, float | None] = {}
    start_time = frame.index[0]

    for name in roi_names:
        entries = frame[f"in_{name}_stable"].diff() == 1
        first_entry_time = entries.idxmax() if entries.any() else None

        if first_entry_time and frame.loc[first_entry_time, f"in_{name}_stable"]:
            results[name] = _to_seconds(first_entry_time - start_time)
        else:
            results[name] = None
    return results


def _entry_counts(frame: pd.DataFrame, roi_names: Any) -> dict[str, int]:
    """Contagem de entradas (transição False→True) em cada ROI."""
    return {name: (frame[f"in_{name}_stable"].astype(int).diff() == 1).sum() for name in roi_names}


def _exit_counts(frame: pd.DataFrame, roi_names: Any) -> dict[str, int]:
    """Contagem de saídas (transição True→False) de cada ROI."""
    return {name: (frame[f"in_{name}_stable"].astype(int).diff() == -1).sum() for name in roi_names}


def _distance_in_rois(frame: pd.DataFrame, roi_names: Any) -> dict[str, float]:
    """Distância percorrida dentro de cada ROI, para o quadro dado.

    O ``diff`` aqui é seguro porque o quadro recebido é sempre de um único
    sujeito (ou a sessão inteira, quando só há um).
    """
    if "segment_dist" not in frame.columns:
        frame["segment_dist"] = np.sqrt(
            frame["x_cm_smoothed"].diff() ** 2 + frame["y_cm_smoothed"].diff() ** 2
        )

    return {name: frame.loc[frame[f"in_{name}_stable"], "segment_dist"].sum() for name in roi_names}


class ROI:
    """A simple class to hold ROI data (name, geometry, and coordinate space)."""

    def __init__(
        self,
        name: str,
        geometry: BaseGeometry,
        coordinate_space: Literal["px", "cm"] = "cm",
    ):
        """Initialize an ROI (Region of Interest).

        Args:
            name: ROI name identifier.
            geometry: Shapely geometry object defining the ROI.
            coordinate_space: Coordinate system ("px" or "cm", default: "cm").
            color: Optional RGB color tuple for visualization.

        """
        self.name = name
        self.geometry = geometry
        self.coordinate_space = coordinate_space


class ROIAnalyzer:
    """Performs spatial and behavioral analysis based on defined ROIs."""

    def __init__(
        self,
        behavior_analyzer: BehavioralAnalyzer,
        rois: list[ROI],
        flutter_n_frames: int | None = None,
        inclusion_rule: str = "bbox_intersects",
        buffer_radius_value: float | None = None,
        min_bbox_overlap_ratio: float | None = None,
        bbox_overlap_basis: str | None = None,
        flutter_enter_frames: int | None = None,
        flutter_exit_frames: int | None = None,
        min_visit_s: float | None = None,
        min_gap_s: float | None = None,
        max_gap_s: float | None = None,
    ):
        """Initialize the ROIAnalyzer.

        Args:
            behavior_analyzer (BehavioralAnalyzer): An instance of
                BehavioralAnalyzer containing the full trajectory data.
            rois (List[ROI]): A list of ROI objects to be analyzed.
            flutter_n_frames (int | None): **Legacy**. Symmetric debounce
                window; maps to both ``flutter_enter_frames`` and
                ``flutter_exit_frames`` when neither is given explicitly.
            inclusion_rule (str): Rule for determining ROI inclusion.
                Options: "centroid_in", "centroid_in_on_buffered_roi",
                "bbox_intersects", "seg_overlap"
            buffer_radius_value (float | None): Radius for buffered ROI rule,
                in cm (converted to px by the geometric mean of the
                calibration). None falls back to the canonical default.
            min_bbox_overlap_ratio (float | None): Minimum overlap fraction
                for the bbox rule. 0.0 means "any non-zero overlap area"
                (tangency excluded). None falls back to the canonical default.
            bbox_overlap_basis (str | None): Denominator of that fraction —
                "bbox", "roi" or "max". None falls back to "bbox".
            flutter_enter_frames (int | None): Consecutive frames inside
                required to confirm an entry. The transition is backdated to
                the first frame of the run.
            flutter_exit_frames (int | None): Consecutive frames outside
                required to confirm an exit (also backdated).
            min_visit_s (float | None): Visits shorter than this (in seconds)
                are discarded. 0.0 disables it.
            min_gap_s (float | None): Gaps shorter than this (in seconds) merge
                the two adjacent visits. 0.0 disables it.
            max_gap_s (float | None): Cap on the time credited to an ROI for a
                single trajectory step. ``None`` = automatic
                (``MAX_GAP_AUTO_FACTOR`` × median observed interval);
                ``math.inf`` = no cap.

        Note:
            Passing ``flutter_enter_frames=1``, ``flutter_exit_frames=1``,
            ``min_visit_s=0.0``, ``min_gap_s=0.0`` and ``max_gap_s=math.inf``
            reproduces the historical (unfiltered, uncapped) output exactly.

        """
        self._b_analyzer = behavior_analyzer
        self._rois = {roi.name: roi for roi in rois}
        self._trajectory = self._b_analyzer.trajectory_data.copy()
        # Eixo de sujeito. ``trajectory_data`` preserva a ordem das linhas, então
        # os rótulos posicionais do analisador comportamental valem aqui.
        self._is_multi_track, self._track_labels, self._track_keys, self._track_positions = (
            self._resolve_track_axis(behavior_analyzer)
        )
        self._inclusion_rule = inclusion_rule
        # Os parâmetros passam pela MESMA normalização do RoiRuleConfig: as
        # faixas dependem da regra e um valor fora delas (um limiar negativo,
        # p.ex., que faria `ratio >= limiar` valer até para caixas que não
        # tocam a ROI) precisa cair no default com log, não seguir para a
        # geometria. `x or default` também não serve: `0.0 or 0.10` é 0.10, e
        # 0.0 é justamente o limiar que pede o predicado de sobreposição pura.
        # A regra segue CRUA em `_inclusion_rule` — uma regra desconhecida deve
        # continuar levantando no dispatcher, não virar a default em silêncio.
        rule_config = RoiRuleConfig(
            rule=(
                inclusion_rule
                if inclusion_rule in VALID_ROI_INCLUSION_RULES
                else DEFAULT_ROI_INCLUSION_RULE
            ),
            buffer_radius_value=(
                DEFAULT_BUFFER_RADIUS_VALUE if buffer_radius_value is None else buffer_radius_value
            ),
            min_bbox_overlap_ratio=(
                DEFAULT_MIN_BBOX_OVERLAP_RATIO
                if min_bbox_overlap_ratio is None
                else min_bbox_overlap_ratio
            ),
            bbox_overlap_basis=(
                DEFAULT_BBOX_OVERLAP_BASIS if bbox_overlap_basis is None else bbox_overlap_basis
            ),
            # ``flutter_n_frames`` é a entrada LEGADA e mapeia para os dois
            # lados; um parâmetro explícito sempre vence. Cada `is None` cai no
            # default canônico SEM log — ausência não é valor inválido.
            flutter_enter_frames=_first_not_none(
                flutter_enter_frames, flutter_n_frames, DEFAULT_ROI_FLUTTER_ENTER_FRAMES
            ),
            flutter_exit_frames=_first_not_none(
                flutter_exit_frames, flutter_n_frames, DEFAULT_ROI_FLUTTER_EXIT_FRAMES
            ),
            min_visit_s=DEFAULT_ROI_MIN_VISIT_S if min_visit_s is None else min_visit_s,
            min_gap_s=DEFAULT_ROI_MIN_GAP_S if min_gap_s is None else min_gap_s,
            max_gap_s=DEFAULT_ROI_MAX_GAP_S if max_gap_s is None else max_gap_s,
        )
        self._buffer_radius_value = rule_config.buffer_radius_value
        self._min_bbox_overlap_ratio = rule_config.min_bbox_overlap_ratio
        self._bbox_overlap_basis = rule_config.bbox_overlap_basis
        self._overlap_any = rule_config.overlap_any
        self._flutter_enter = rule_config.flutter_enter_frames
        self._flutter_exit = rule_config.flutter_exit_frames
        self._min_visit_s = rule_config.min_visit_s
        self._min_gap_s = rule_config.min_gap_s
        self._max_gap_s = rule_config.max_gap_s
        # Relógio em segundos com o ``dt`` JÁ limitado, e o tempo que o teto
        # descartou. Ambos preenchidos por ``_prepare_time_base``.
        self._clock_s: np.ndarray = np.zeros(0, dtype=float)
        # Um relógio por animal (mesma forma de soma-prefixo exclusiva). Com um
        # único sujeito é ``[self._clock_s]``.
        self._track_clocks: list[np.ndarray] = []
        self._unobserved_time_s: float = 0.0
        self._unobserved_by_track: dict[Any, float] = {}
        # Mapa (timestamp[, track]) -> linha, montado sob demanda por
        # ``_episode_row``.
        self._episode_row_index: dict[Any, int] | None = None
        # Visão de GRUPO: uma linha por instante, ocupação = "algum animal
        # dentro" (semântica ``any_track``, a mesma do ``ArduinoEventMapper``).
        # Com um único sujeito é o PRÓPRIO ``_trajectory`` — o caminho histórico
        # segue byte a byte o mesmo.
        self._view: pd.DataFrame = self._trajectory
        self._buffered_rois_cache: dict[str, Any] = {}  # Cache for buffered ROI geometries
        self._roi_geometries_px = self._normalize_roi_geometries()
        self._validate_rois()
        self._calculate_presence_in_rois()

    def _resolve_track_axis(
        self, behavior_analyzer: BehavioralAnalyzer
    ) -> tuple[bool, np.ndarray, list[Any], list[np.ndarray]]:
        """Extrai o eixo de sujeito do analisador comportamental.

        A adesão é verificada, não presumida: o eixo só é aceito se
        ``is_multi_track`` for literalmente ``True`` e os rótulos vierem como um
        ``ndarray`` do tamanho da trajetória. Um analisador substituto (mock,
        adaptador antigo) devolve objetos truthy para qualquer atributo, e
        aceitá-los faria a análise entrar no caminho multi-animal com um
        agrupador de tamanho errado. Sem eixo válido, a análise é de sujeito
        único — que é o comportamento histórico.
        """
        n_rows = len(self._trajectory)
        single: tuple[bool, np.ndarray, list[Any], list[np.ndarray]] = (
            False,
            np.zeros(n_rows, dtype=np.int64),
            [],
            [np.arange(n_rows)],
        )

        if getattr(behavior_analyzer, "is_multi_track", False) is not True:
            return single

        labels = getattr(behavior_analyzer, "track_labels", None)
        if not isinstance(labels, np.ndarray) or labels.size != n_rows:
            return single

        keys = getattr(behavior_analyzer, "track_keys", None)
        if not isinstance(keys, list) or not keys:
            return single

        labels = np.asarray(labels, dtype=np.int64)
        # As posições são recalculadas aqui em vez de lidas do analisador: são
        # derivadas dos rótulos que acabaram de ser validados, e assim não há
        # como as duas visões discordarem.
        positions = [np.flatnonzero(labels == label) for label in range(len(keys))]
        return True, labels, list(keys), positions

    @property
    def rois(self) -> dict[str, ROI]:
        """Returns the dictionary of ROI objects."""
        return self._rois

    @property
    def is_multi_track(self) -> bool:
        """``True`` quando a trajetória analisada contém mais de um animal."""
        return self._is_multi_track

    @property
    def track_keys(self) -> list[Any]:
        """``track_id`` de cada animal presente na trajetória."""
        return list(self._track_keys)

    def _validate_rois(self):
        """Check for empty or invalid ROIs."""
        if not self._rois:
            raise ValueError("ROI list cannot be empty.")
        for name, _roi in self._rois.items():
            geometry = self._roi_geometries_px[name]
            if not isinstance(geometry, BaseGeometry) or geometry.is_empty:
                raise ValueError(f"ROI '{name}' has invalid geometry.")

    def _normalize_roi_geometries(self) -> dict[str, BaseGeometry]:
        """Convert ROI geometries to warped pixel space when necessary."""
        normalized: dict[str, BaseGeometry] = {}
        pixelcm_x = getattr(self._b_analyzer, "_pixelcm_x", 1.0)
        pixelcm_y = getattr(self._b_analyzer, "_pixelcm_y", 1.0)
        height_px = getattr(self._b_analyzer, "_video_height_px", 0)

        for name, roi in self._rois.items():
            geometry = roi.geometry
            if roi.coordinate_space == "cm":
                geometry = affinity.affine_transform(
                    geometry,
                    [
                        float(pixelcm_x),
                        0.0,
                        0.0,
                        float(-pixelcm_y),
                        0.0,
                        float(height_px),
                    ],
                )
            normalized[name] = geometry

        return normalized

    def _buffer_radius_px(self) -> float:
        px_per_cm_x = getattr(self._b_analyzer, "_pixelcm_x", 1.0)
        px_per_cm_y = getattr(self._b_analyzer, "_pixelcm_y", 1.0)
        return float(self._buffer_radius_value) * np.sqrt(px_per_cm_x * px_per_cm_y)

    def _get_centers_px(self) -> tuple[np.ndarray, np.ndarray]:
        if (
            "x_center_px" in self._trajectory.columns
            and "y_center_px" in self._trajectory.columns
            and not self._trajectory["x_center_px"].isna().all()
        ):
            x_coords = self._trajectory["x_center_px"].to_numpy()
            y_coords = self._trajectory["y_center_px"].to_numpy()
            return x_coords, y_coords

        if all(col in self._trajectory.columns for col in ["x1", "y1", "x2", "y2"]):
            x_coords = ((self._trajectory["x1"] + self._trajectory["x2"]) / 2).to_numpy()
            y_coords = ((self._trajectory["y1"] + self._trajectory["y2"]) / 2).to_numpy()
            return x_coords, y_coords

        raise ValueError("Cannot find suitable pixel coordinate columns in trajectory data")

    @property
    def unobserved_time_s(self) -> float:
        """Tempo descartado pelo teto de ``dt``, em segundos.

        É o tempo de sessão que NÃO foi medido: lacunas de rastreamento em que
        o animal esteve em lugar nenhum conhecido. Sem o teto esse tempo era
        creditado por inteiro à ROI onde o animal reapareceu — uma perda de 5 s
        virava 5 s "dentro" dessa ROI.
        """
        return self._unobserved_time_s

    @property
    def unobserved_time_s_by_track(self) -> dict[Any, float]:
        """Tempo não observado de CADA animal, em segundos.

        Vazio quando há um único sujeito: nesse caso
        :attr:`unobserved_time_s` já é o número por animal.
        """
        return dict(self._unobserved_by_track)

    def _prepare_time_base(self) -> None:
        """Preenche a coluna ``dt``, aplica o teto e monta o relógio observado.

        O teto (:attr:`_max_gap_s`) resolve o defeito de atribuição de tempo: o
        DataFrame só tem linhas onde HOUVE detecção, então o ``dt`` da primeira
        linha depois de uma lacuna vale a lacuna inteira. O excedente não é
        creditado a ROI nenhuma — vai para :attr:`unobserved_time_s`.

        A coluna ``dt`` só é reescrita nas linhas que o teto realmente corta.
        Reescrevê-la inteira converteria ``Timedelta`` → segundos → ``Timedelta``
        e introduziria arredondamento onde nada precisava mudar (o modo neutro
        precisa ser idêntico BIT A BIT ao histórico).
        """
        index_series = self._trajectory.index.to_series()
        # Por sujeito: um ``diff`` global sobre linhas de animais intercaladas
        # devolveria zero (mesmo timestamp, animais diferentes) no lugar do
        # intervalo real entre dois frames do MESMO animal.
        self._trajectory["dt"] = (
            index_series.groupby(self._track_labels).diff()
            if self._is_multi_track
            else index_series.diff()
        )

        dt_column = self._trajectory["dt"]
        is_timedelta = getattr(dt_column.dtype, "kind", "") == "m"
        dt_seconds = (
            dt_column.dt.total_seconds().to_numpy(dtype=float)
            if is_timedelta
            else pd.to_numeric(dt_column, errors="coerce").to_numpy(dtype=float)
        )
        # O primeiro frame não tem ``dt`` (NaN): não representa tempo algum.
        dt_seconds = np.nan_to_num(dt_seconds, nan=0.0, posinf=0.0, neginf=0.0)

        cap = self._resolve_max_gap(dt_seconds)
        self._unobserved_time_s = 0.0
        capped = dt_seconds
        if np.isfinite(cap):
            exceeds = dt_seconds > cap
            if exceeds.any():
                capped = np.minimum(dt_seconds, cap)
                self._unobserved_time_s = float(np.sum(dt_seconds[exceeds] - cap))
                cap_value = pd.Timedelta(seconds=cap) if is_timedelta else cap
                # Posicional, não por rótulo: o índice da trajetória pode ter
                # timestamps repetidos, e um ``.loc`` neles reescreveria linhas
                # que o teto não cortou.
                self._trajectory.iloc[
                    np.flatnonzero(exceeds), self._trajectory.columns.get_loc("dt")
                ] = cap_value

        # Relógio monotônico do tempo OBSERVADO, em soma-prefixo EXCLUSIVA
        # (tamanho n+1, começando em 0). Com essa forma,
        # ``clock[fim] - clock[início]`` é a soma do ``dt`` dos frames
        # ``[início, fim)`` — exatamente o tempo que ``get_time_spent_in_rois``
        # credita a esses frames.
        #
        # A soma INCLUSIVA anterior media ``t[fim] - t[início]``, que embute o
        # ``dt`` do frame ``fim`` — o primeiro frame FORA da visita. Se esse
        # frame fosse o reaparecimento depois de uma lacuna, o ``dt`` dele
        # (ainda que limitado pelo teto) inflava a duração da visita ANTERIOR,
        # que é justamente o que o teto existe para impedir.
        self._clock_s = np.concatenate(([0.0], np.cumsum(capped)))

        if not self._is_multi_track:
            self._track_clocks = [self._clock_s]
            return

        # UM relógio POR ANIMAL, cada um com o seu próprio zero. Não cabem num
        # array só: a soma-prefixo exclusiva tem uma posição a mais que os
        # frames que descreve, e um cumsum global somaria os intervalos de
        # todos os peixes — qualquer visita pareceria N vezes mais longa.
        excess = dt_seconds - capped
        self._track_clocks = []
        self._unobserved_by_track = {}
        for label, positions in enumerate(self._track_positions):
            self._track_clocks.append(
                np.concatenate(([0.0], np.cumsum(capped[positions])))
                if positions.size
                else np.zeros(1, dtype=float)
            )
            if positions.size:
                self._unobserved_by_track[self._track_keys[label]] = float(excess[positions].sum())

    def _resolve_max_gap(self, dt_seconds: np.ndarray) -> float:
        """Teto efetivo de ``dt``, em segundos (``inf`` = sem teto)."""
        if self._max_gap_s is not None:
            return float(self._max_gap_s)

        positive = dt_seconds[dt_seconds > 0.0]
        if positive.size == 0:
            # Série de um frame só (ou timestamps repetidos): não há intervalo
            # nominal do qual derivar um teto.
            return float(np.inf)
        return float(MAX_GAP_AUTO_FACTOR * np.median(positive))

    def _apply_flutter_filter(self, raw_presence: pd.Series) -> pd.Series:
        """Debounce de presença COM RETRODATAÇÃO.

        Uma entrada é confirmada por ``flutter_enter_frames`` frames dentro
        consecutivos, e uma saída por ``flutter_exit_frames`` frames fora — mas
        a transição confirmada é REGISTRADA no PRIMEIRO frame da sequência, não
        no frame em que a confirmação se completou.

        A retrodatação é o que torna o filtro utilizável. A implementação
        anterior usava ``rolling(N).min()/max()``, que é uma janela
        retardatária: a transição aparecia N-1 frames depois de acontecer e
        enviesava ``latencia_primeira_entrada`` e ``tempo_gasto_por_roi``
        proporcionalmente a N. Foi por isso que a produção passou a fixar N=1 —
        o viés só sumia desligando o filtro.

        A borda inicial é explícita: o estado começa FORA e só muda com uma
        sequência completa. O ``min_periods=1`` de antes deixava o primeiro
        frame definir o estado sozinho, sem confirmação nenhuma.

        Args:
            raw_presence (pd.Series): The raw boolean series of presence.

        Returns:
            pd.Series: The stabilized boolean series.

        """
        if self._flutter_enter <= 1 and self._flutter_exit <= 1:
            # Sem janela de confirmação, a série estável É a série crua.
            return raw_presence

        values = raw_presence.to_numpy(dtype=bool)
        if values.size == 0:
            return raw_presence

        # Fronteiras das sequências de valor constante.
        starts = np.concatenate(([0], np.flatnonzero(np.diff(values)) + 1))
        ends = np.concatenate((starts[1:], [values.size]))

        stable = np.zeros(values.size, dtype=bool)
        state = False
        last_change = 0
        for start, end in zip(starts, ends, strict=True):
            value = bool(values[start])
            if value == state:
                continue
            if (end - start) < (self._flutter_enter if value else self._flutter_exit):
                continue
            # Retrodatação: tudo até ``start`` mantém o estado anterior, e o
            # novo estado vale a partir do PRIMEIRO frame da sequência.
            stable[last_change:start] = state
            state = value
            last_change = start
        stable[last_change:] = state

        return pd.Series(stable, index=raw_presence.index)

    def _stabilize_presence(self, raw_presence: pd.Series) -> pd.Series:
        """Debounce + filtro de duração, SEMPRE dentro de um mesmo animal.

        Os dois filtros procuram sequências numa série ordenada de UM sujeito.
        Aplicados a linhas de animais intercaladas, as sequências alternam entre
        peixes e o resultado não significa nada: N frames "dentro" poderiam ser
        N animais distintos passando uma vez cada.
        """
        if not self._is_multi_track:
            return self._apply_duration_filter(
                self._apply_flutter_filter(raw_presence), self._clock_s
            )

        stabilized = np.zeros(len(raw_presence), dtype=bool)
        for label, positions in enumerate(self._track_positions):
            if positions.size == 0:
                continue
            sub_presence = raw_presence.iloc[positions]
            # O relógio DAQUELE animal, não uma fatia do relógio global: cada um
            # é uma soma-prefixo exclusiva com o seu próprio zero.
            sub_result = self._apply_duration_filter(
                self._apply_flutter_filter(sub_presence), self._track_clocks[label]
            )
            stabilized[positions] = sub_result.to_numpy(dtype=bool)

        return pd.Series(stabilized, index=raw_presence.index)

    def _apply_duration_filter(self, stable_presence: pd.Series, clock: np.ndarray) -> pd.Series:
        """Descarta visitas curtas demais e funde lacunas curtas demais.

        Roda DEPOIS do debounce, nunca antes: aplicar o limiar de duração sobre
        a presença crua mediria a duração de eventos que o debounce ainda vai
        remover ou retrodatar, e o resultado seria diferente (e errado).

        As durações saem do relógio de tempo OBSERVADO
        (:meth:`_prepare_time_base`), então uma lacuna de rastreamento não
        infla artificialmente a duração da visita que a contém.

        A duração de um intervalo ``[início, fim)`` é o tempo CREDITADO aos
        frames do próprio intervalo — a mesma soma que
        :meth:`get_time_spent_in_rois` faz. Ou seja: "descartar visitas com
        menos de ``min_visit_s``" quer dizer, literalmente, "descartar visitas
        a que menos de ``min_visit_s`` seria creditado".

        Medir de outro jeito reintroduziria o defeito: usar o intervalo até o
        primeiro frame FORA (``t[fim] - t[início]``) embute o ``dt`` desse
        frame, e se ele for o reaparecimento depois de uma lacuna, a lacuna
        infla a visita anterior.
        """
        if self._min_visit_s <= 0.0 and self._min_gap_s <= 0.0:
            return stable_presence

        values = stable_presence.to_numpy(dtype=bool)
        n = values.size
        # O relógio é soma-prefixo exclusiva: n+1 posições para n frames.
        if n == 0 or clock.size != n + 1:
            return stable_presence

        # Bordas das visitas: +1 entra, -1 sai. O ``pad`` com False nas duas
        # pontas faz uma visita que começa no frame 0 (ou termina no último)
        # aparecer como qualquer outra, sem caso especial.
        padded = np.concatenate(([False], values, [False])).astype(np.int8)
        edges = np.flatnonzero(np.diff(padded))
        starts = edges[0::2]
        ends = edges[1::2]  # exclusivo

        visits: list[list[int]] = []
        for start, end in zip(starts, ends, strict=True):
            if (
                visits
                and self._min_gap_s > 0.0
                and (clock[start] - clock[visits[-1][1]]) < self._min_gap_s
            ):
                # Lacuna curta demais: as duas visitas são a mesma. A lacuna é
                # medida com a MESMA regra da visita — o tempo creditado aos
                # frames de fora, ``[fim_anterior, início)``.
                visits[-1][1] = int(end)
                continue
            visits.append([int(start), int(end)])

        filtered = np.zeros(n, dtype=bool)
        for start, end in visits:
            # Sem ``min(end, n-1)``: a soma-prefixo exclusiva tem n+1 posições,
            # então uma visita que vai até o fim da série (``end == n``) não é
            # mais um caso especial.
            duration = clock[end] - clock[start]
            if self._min_visit_s > 0.0 and duration < self._min_visit_s:
                continue
            filtered[start:end] = True

        return pd.Series(filtered, index=stable_presence.index)

    def _calculate_presence_in_rois(self):
        """Calculate raw and stable presence for each ROI.

        Ordem das operações — mudá-la muda os números:
        presença crua → debounce/retrodatação → filtro de duração
        (visita/lacuna) → série estável → métricas.

        Also creates a single column with the current stable ROI name.

        Com mais de um animal, ``in_{roi}_stable`` continua sendo a presença
        DAQUELE animal na linha; a ocupação de grupo mora em :attr:`_view`.
        """
        self._prepare_time_base()

        # Determine coordinate space and extract coordinates
        x_coords, y_coords = self._get_centers_px()

        for name, roi_geometry in self._roi_geometries_px.items():
            raw_presence = self._calculate_roi_presence_by_rule(
                roi_geometry, name, x_coords, y_coords
            )

            self._trajectory[f"in_{name}_stable"] = self._stabilize_presence(raw_presence)

        # Create a single column with the name of the ROI the animal is in
        _assign_stable_roi(self._trajectory, self._rois)

        self._view = self._build_group_view() if self._is_multi_track else self._trajectory

    def _build_group_view(self) -> pd.DataFrame:
        """Linha do tempo de OCUPAÇÃO do grupo: uma linha por instante.

        A ROI conta como ocupada enquanto QUALQUER animal estiver dentro
        (semântica ``any_track``). É a mesma leitura que o
        ``ArduinoEventMapper`` usa ao vivo para acionar o hardware, de modo que
        relatório e equipamento voltem a descrever o mesmo evento.

        Existe porque as métricas de grupo não podem somar as linhas por animal:
        ``dt`` ali é o intervalo DAQUELE animal, e somá-lo sobre N peixes daria
        N × a duração da sessão.
        """
        stable_cols = [f"in_{name}_stable" for name in self._rois]
        view = self._trajectory.groupby(level=0, sort=True)[stable_cols].any()

        index_series = view.index.to_series()
        view["dt"] = index_series.diff()
        dt_seconds = view["dt"].dt.total_seconds().to_numpy(dtype=float)
        dt_seconds = np.nan_to_num(dt_seconds, nan=0.0, posinf=0.0, neginf=0.0)

        # O mesmo teto de lacuna das séries individuais, agora sobre a linha do
        # tempo do grupo: a sessão só é "não observada" quando NENHUM animal
        # foi visto.
        cap = self._resolve_max_gap(dt_seconds)
        self._unobserved_time_s = 0.0
        if np.isfinite(cap):
            exceeds = dt_seconds > cap
            if exceeds.any():
                self._unobserved_time_s = float(np.sum(dt_seconds[exceeds] - cap))
                view.iloc[np.flatnonzero(exceeds), view.columns.get_loc("dt")] = pd.Timedelta(
                    seconds=cap
                )

        _assign_stable_roi(view, self._rois)
        return view

    def _calculate_roi_presence_by_rule(
        self,
        roi_geometry: BaseGeometry,
        roi_name: str,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
    ) -> pd.Series:
        """Calculate presence in ROI based on the configured inclusion rule."""
        if self._inclusion_rule == "centroid_in":
            return self._calculate_centroid_in(roi_geometry, x_coords, y_coords)
        elif self._inclusion_rule == "centroid_in_on_buffered_roi":
            return self._calculate_centroid_in_buffered(roi_geometry, roi_name, x_coords, y_coords)
        elif self._inclusion_rule == "bbox_intersects":
            return self._calculate_bbox_intersects(roi_geometry, x_coords, y_coords)
        elif self._inclusion_rule == "seg_overlap":
            return self._calculate_seg_overlap(roi_geometry)
        else:
            raise ValueError(f"Unknown inclusion rule: {self._inclusion_rule}")

    def _calculate_centroid_in(
        self, roi_geometry: BaseGeometry, x_coords: np.ndarray, y_coords: np.ndarray
    ) -> pd.Series:
        """Calculate presence using centroid inclusion (current behavior)."""
        prepare(roi_geometry)
        points = shapely.points(x_coords, y_coords)
        raw_presence_np = shapely.contains(roi_geometry, points)
        return pd.Series(raw_presence_np, index=self._trajectory.index)

    def _calculate_centroid_in_buffered(
        self,
        roi_geometry: BaseGeometry,
        roi_name: str,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
    ) -> pd.Series:
        """Calculate presence using buffered ROI and centroid inclusion."""
        # Use cached buffered geometry if available
        cache_key = f"{roi_name}_px_{self._buffer_radius_value}"
        if cache_key not in self._buffered_rois_cache:
            buffer_radius = self._buffer_radius_px()
            self._buffered_rois_cache[cache_key] = roi_geometry.buffer(buffer_radius)

        buffered_roi = self._buffered_rois_cache[cache_key]
        prepare(buffered_roi)
        points = shapely.points(x_coords, y_coords)
        raw_presence_np = shapely.contains(buffered_roi, points)
        return pd.Series(raw_presence_np, index=self._trajectory.index)

    def _calculate_bbox_intersects(
        self, roi_geometry: BaseGeometry, x_coords: np.ndarray, y_coords: np.ndarray
    ) -> pd.Series:
        """Calculate presence based on bbox intersection with ROI."""
        # Require bbox columns
        required_cols = ["x1", "y1", "x2", "y2"]
        missing_cols = [col for col in required_cols if col not in self._trajectory.columns]
        if missing_cols:
            raise ValueError(
                f"Regra bbox_intersects requer colunas de bbox: {missing_cols}. "
                f"Essas colunas não estão disponíveis no dataset. "
                f"Considere usar 'centroid_in' ou 'centroid_in_on_buffered_roi'."
            )

        prepare(roi_geometry)

        # Vectorized calculation for performance optimization
        x1_px = self._trajectory["x1"].to_numpy()
        y1_px = self._trajectory["y1"].to_numpy()
        x2_px = self._trajectory["x2"].to_numpy()
        y2_px = self._trajectory["y2"].to_numpy()

        min_x = np.minimum(x1_px, x2_px)
        max_x = np.maximum(x1_px, x2_px)
        min_y = np.minimum(y1_px, y2_px)
        max_y = np.maximum(y1_px, y2_px)

        # Vectorized box creation
        bboxes = shapely.box(min_x, min_y, max_x, max_y)

        if self._overlap_any:
            # Limiar 0: qualquer sobreposição de área não-nula conta. Resolvido
            # pelo predicado topológico, sem razão de áreas — mais barato e
            # imune ao ruído de ponto flutuante perto da tangência.
            raw_presence_np = shapely.relate_pattern(roi_geometry, bboxes, _INTERIORS_INTERSECT)
            return pd.Series(raw_presence_np, index=self._trajectory.index)

        # Vectorized intersection
        intersections = shapely.intersection(roi_geometry, bboxes)

        # Vectorized area calculation
        intersection_areas = shapely.area(intersections)
        bbox_areas = shapely.area(bboxes)
        roi_area = float(shapely.area(roi_geometry))

        # Avoid division by zero.
        # A bbox degenerada (área 0) e uma ROI degenerada dão razão 0 — o
        # nan_to_num cobre os dois denominadores.
        with np.errstate(divide="ignore", invalid="ignore"):
            by_bbox = np.nan_to_num(
                intersection_areas / bbox_areas, nan=0.0, posinf=0.0, neginf=0.0
            )
            by_roi = np.nan_to_num(
                intersection_areas / roi_area if roi_area else np.zeros_like(intersection_areas),
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            )

        if self._bbox_overlap_basis == "roi":
            ratios = by_roi
        elif self._bbox_overlap_basis == "max":
            ratios = np.maximum(by_bbox, by_roi)
        else:
            ratios = by_bbox

        raw_presence_np = ratios >= self._min_bbox_overlap_ratio

        return pd.Series(raw_presence_np, index=self._trajectory.index)

    def _calculate_seg_overlap(self, roi_geometry: BaseGeometry) -> pd.Series:
        """Calculate presence based on segmentation mask overlap."""
        # Check for segmentation data columns
        # Note: We don't persist segmentation masks in this PR,
        # so this will always error
        raise ValueError(
            "Regra seg_overlap requer dados de segmentação que não estão "
            "disponíveis neste dataset. "
            "Por favor, selecione outra regra de inclusão (centroid_in, "
            "centroid_in_on_buffered_roi, ou bbox_intersects)."
        )

    def get_time_spent_in_rois(self) -> dict[str, dict[str, float]]:
        """Calculate the total time (seconds and percentage) spent in each ROI.

        Com mais de um animal os números são de OCUPAÇÃO da ROI (``any_track``):
        o tempo em que ao menos um animal esteve dentro, não a soma dos tempos
        individuais. Para os números por sujeito use :meth:`get_metrics_by_track`.

        Returns:
            Dictionary mapping ROI names to dictionaries with 'seconds' and
            'percentage' keys.

        """
        return _time_spent_in_rois(self._view, self._rois)

    def get_latency_to_first_entry(self) -> dict[str, float | None]:
        """Calculate the latency to the first entry into each ROI.

        Multi-animal: latência até a PRIMEIRA ocupação da ROI por qualquer
        animal.

        Returns:
            Dictionary mapping ROI names to latency in seconds (float) or None
            if the animal never enters that ROI.

        """
        return _latency_to_first_entry(self._view, self._rois)

    def get_entry_counts(self) -> dict[str, int]:
        """Count the number of entries into each ROI.

        Multi-animal: transições de "ROI vazia" para "ROI ocupada". Duas
        entradas simultâneas de animais diferentes são UMA ocupação — as
        contagens por sujeito estão em :meth:`get_metrics_by_track`.

        Returns:
            Dictionary mapping ROI names to entry counts.

        """
        return _entry_counts(self._view, self._rois)

    def get_exit_counts(self) -> dict[str, int]:
        """Count the number of exits from each ROI.

        Multi-animal: transições de "ROI ocupada" para "ROI vazia".

        Returns:
            Dictionary mapping ROI names to exit counts.

        """
        return _exit_counts(self._view, self._rois)

    def get_metrics_by_track(self) -> dict[str, dict[str, Any]]:
        """Métricas de ROI POR ANIMAL, indexadas pelo ``track_id``.

        É o cálculo cientificamente primário: cada animal tem a sua própria
        série de presença, o seu próprio relógio e as suas próprias entradas e
        saídas. Os números publicados no topo de ``analise_roi`` são a
        AGREGAÇÃO ``any_track`` desta base.

        Com um único sujeito devolve esse sujeito num dicionário de um item —
        os valores coincidem com os das métricas de grupo.

        Returns:
            ``{track_id_str: {"tempo_gasto_por_roi": ..., ...}}``.

        """
        results: dict[str, dict[str, Any]] = {}
        for label, positions in enumerate(self._track_positions):
            if positions.size == 0:
                continue
            key = self._track_keys[label] if self._is_multi_track else self._sole_track_key()
            frame = self._trajectory.iloc[positions].copy()
            results[str(key)] = {
                "tempo_gasto_por_roi": _time_spent_in_rois(frame, self._rois),
                "latencia_primeira_entrada": _latency_to_first_entry(frame, self._rois),
                "contagem_entradas": _entry_counts(frame, self._rois),
                "contagem_saidas": _exit_counts(frame, self._rois),
                "distancia_por_roi": _distance_in_rois(frame, self._rois),
                "tempo_nao_observado_s": self._unobserved_by_track.get(
                    key, self._unobserved_time_s if not self._is_multi_track else 0.0
                ),
            }
        return results

    def _sole_track_key(self) -> Any:
        """``track_id`` do único sujeito, quando existe a coluna."""
        if "track_id" not in self._trajectory.columns or self._trajectory.empty:
            return 0
        first = self._trajectory["track_id"].iloc[0]
        return 0 if pd.isna(first) else first

    def get_inter_visit_latencies(self) -> dict[str, list[float]]:
        """Calculate latencies for re-entries into each ROI.

        A re-entry latency is the time from the last exit from ANY ROI to the
        next entry into the specified ROI.

        Returns:
            Dictionary mapping ROI names to lists of inter-visit latency values
            in seconds.

        """
        results = {}

        # Get all timestamps where the animal exits ANY ROI to 'Outside'
        exited_any_roi = (self._view["stable_roi"] != "Outside") & (
            self._view["stable_roi"].shift(-1) == "Outside"
        )
        all_exit_times = self._view[exited_any_roi].index

        for name in self._rois:
            latencies = []
            # Get all entry timestamps for the current ROI
            entries = self._view[f"in_{name}_stable"].diff() == 1
            entry_times = self._view[entries].index

            # For each entry, find the most recent prior exit from any ROI
            for entry_time in entry_times:
                # Find the index of the exit that would be just before this entry
                # 'right' means if timestamps are equal, exit is considered after
                idx = all_exit_times.searchsorted(entry_time, side="right")
                if idx > 0:
                    # The most recent exit is at the previous index
                    last_exit_time = all_exit_times[idx - 1]
                    latencies.append(entry_time - last_exit_time)

            results[name] = latencies
        return results

    def get_roi_transitions(self) -> pd.DataFrame:
        """Calculate a transition matrix showing ROI transitions.

        Show the count of direct movements between ROIs (and 'Outside').

        Returns:
            DataFrame with transition counts from one ROI/state to another.

        """
        states = self._view["stable_roi"]
        # Compare current state with the state in the previous frame
        transitions = pd.crosstab(states, states.shift(-1), dropna=False)
        # Rename for clarity
        transitions.index.name = "From"
        transitions.columns.name = "To"
        return transitions

    def get_event_log(self) -> pd.DataFrame:
        """Generate a sequential log of all entry and exit events for all ROIs.

        Returns:
            A pandas DataFrame with columns for timestamp, event type, and ROI name,
            sorted chronologically.

        """
        states = self._view["stable_roi"]
        # Find points where the state changes by comparing with the previous state
        state_changes = states[states != states.shift(1)]

        events = []
        # The initial state is an "entry" into wherever the animal starts
        initial_state = states.iloc[0]
        if initial_state != "Outside":
            events.append(
                {
                    "timestamp": states.index[0],
                    "event": "enter",
                    "roi_name": initial_state,
                }
            )

        # Iterate through the changes to log entries and exits
        for timestamp, current_roi in state_changes.items():
            # Skip the very first timestamp, as it's handled by the initial state
            if timestamp == states.index[0]:
                continue

            previous_roi = states.shift(1)[timestamp]

            # Log the exit from the previous ROI
            if previous_roi != "Outside":
                events.append(
                    {
                        "timestamp": timestamp,
                        "event": "exit",
                        "roi_name": previous_roi,
                    }
                )
            # Log the entry into the current ROI
            if current_roi != "Outside":
                events.append(
                    {
                        "timestamp": timestamp,
                        "event": "enter",
                        "roi_name": current_roi,
                    }
                )

        if not events:
            return pd.DataFrame(columns=["timestamp", "event", "roi_name"])

        event_df = pd.DataFrame(events).drop_duplicates()
        event_df.sort_values(by="timestamp", inplace=True)
        return event_df

    def _get_filtered_trajectory(self, roi_name: str) -> pd.DataFrame:
        """Get trajectory segments only within a specific ROI."""
        if f"in_{roi_name}_stable" not in self._trajectory.columns:
            raise ValueError(f"Invalid ROI name: {roi_name}")
        return self._trajectory[self._trajectory[f"in_{roi_name}_stable"]]

    def get_distance_in_rois(self) -> dict[str, float]:
        """Calculate the total distance traveled within each ROI.

        Returns:
            Dictionary mapping ROI names to total distance in centimeters.

        """
        if not self._is_multi_track:
            # Sum the segment distances only for points within the ROI.
            # We consider the distance for a segment to be "in" the ROI if the
            # endpoint of the segment is in the ROI.
            return _distance_in_rois(self._trajectory, self._rois)

        # Com vários animais, a distância de grupo é a SOMA das distâncias
        # individuais percorridas dentro da ROI — não há "o percurso do grupo".
        # O ``diff`` tem de ser por sujeito: entre duas linhas consecutivas de
        # peixes diferentes ele mediria a distância ENTRE os peixes.
        totals = {name: 0.0 for name in self._rois}
        for positions in self._track_positions:
            if positions.size == 0:
                continue
            per_track = _distance_in_rois(self._trajectory.iloc[positions].copy(), self._rois)
            for name, value in per_track.items():
                totals[name] += float(value)
        return totals

    def get_velocity_stats_in_rois(self) -> dict[str, dict[str, float] | None]:
        """Calculate velocity statistics within each ROI.

        Returns:
            Dictionary mapping ROI names to statistics dictionaries with 'mean',
            'median', and 'std_dev' keys, or None if no data available.

        """
        results: dict[str, dict[str, float] | None] = {}
        # Ensure velocity is calculated on the base analyzer
        if "v_mag" not in self._b_analyzer.trajectory_data.columns:
            self._b_analyzer.calculate_velocity_timeseries()

        for name in self._rois:
            roi_traj = self._get_filtered_trajectory(name)
            if roi_traj.empty:
                results[name] = None
                continue

            v_mag = roi_traj["v_mag"].dropna()
            results[name] = {
                "mean": v_mag.mean(),
                "median": v_mag.median(),
                "std_dev": v_mag.std(),
            }
        return results

    def get_freezing_in_rois(
        self, vel_threshold: float, min_duration: float
    ) -> dict[str, dict[str, Any]]:
        """Calculate freezing episodes that occur within each ROI."""
        results = {}
        # Ensure freezing episodes are detected on the base analyzer
        freezing_episodes = self._b_analyzer.detect_freezing_episodes(vel_threshold, min_duration)

        # Índice posicional do início de cada episódio. Com vários animais o
        # timestamp NÃO identifica a linha (é repetido entre sujeitos), então o
        # par (timestamp, track_id) é a única chave que devolve a linha certa;
        # um ``.loc`` só pelo tempo devolveria várias linhas e o teste de
        # verdade explodiria.
        episode_rows = [self._episode_row(episode) for episode in freezing_episodes]

        for name in self._rois:
            roi_episodes = []
            column = self._trajectory[f"in_{name}_stable"].to_numpy(dtype=bool)
            for episode, row in zip(freezing_episodes, episode_rows, strict=True):
                # Check if the episode occurred inside the ROI
                # We can check the start, mid, or end point. Let's use the start.
                if row is not None and column[row]:
                    roi_episodes.append(episode)

            results[name] = {
                "count": len(roi_episodes),
                "total_duration": sum(e["duration"] for e in roi_episodes),
                "episodes": roi_episodes,
            }
        return results

    def get_tortuosity_in_rois(self) -> dict[str, float | None]:
        """Calculate trajectory tortuosity within each ROI.

        Returns:
            Dictionary mapping ROI names to tortuosity values (path length divided
            by straight-line distance) or None if insufficient data.

        """
        if self._is_multi_track:
            # Razão POR PERCURSO: a média das tortuosidades individuais é a
            # única leitura de grupo com significado. Concatenar os peixes num
            # "percurso" só produziria a distância entre eles.
            return self._tortuosity_in_rois_by_track()

        results: dict[str, float | None] = {}
        for name in self._rois:
            roi_traj = self._get_filtered_trajectory(name)
            if len(roi_traj) < 2:
                results[name] = None
                continue

            # Path distance is the sum of segment lengths
            path_distance = np.sqrt(
                roi_traj["x_cm_smoothed"].diff() ** 2 + roi_traj["y_cm_smoothed"].diff() ** 2
            ).sum()

            # Straight-line distance from start to end point
            start_point = roi_traj.iloc[0]
            end_point = roi_traj.iloc[-1]
            straight_dist = np.sqrt(
                (end_point["x_cm_smoothed"] - start_point["x_cm_smoothed"]) ** 2
                + (end_point["y_cm_smoothed"] - start_point["y_cm_smoothed"]) ** 2
            )

            if straight_dist > 0:
                results[name] = path_distance / straight_dist
            else:
                results[name] = np.inf if path_distance > 0 else 1.0
        return results

    def _episode_row(self, episode: dict[str, Any]) -> int | None:
        """Índice POSICIONAL da linha em que um episódio começa.

        Com vários animais o timestamp sozinho não identifica uma linha, então
        a chave é o par (timestamp, ``track_id``) — que é exatamente o par que
        ``detect_freezing_episodes`` carimba em cada episódio.
        """
        if self._episode_row_index is None:
            index_values = self._trajectory.index.to_numpy()
            if self._is_multi_track:
                keys: list[Any] = [
                    (index_values[row], self._track_keys[int(self._track_labels[row])])
                    for row in range(len(index_values))
                ]
            else:
                keys = list(index_values)
            # O primeiro vencedor fica: espelha o ``.loc`` histórico, que
            # devolvia a primeira linha do rótulo.
            mapping: dict[Any, int] = {}
            for row, key in enumerate(keys):
                mapping.setdefault(key, row)
            self._episode_row_index = mapping

        if self._is_multi_track:
            return self._episode_row_index.get((episode["start_time"], episode.get("track_id")))
        return self._episode_row_index.get(episode["start_time"])

    def _tortuosity_in_rois_by_track(self) -> dict[str, float | None]:
        """Média das tortuosidades individuais dentro de cada ROI."""
        per_roi: dict[str, list[float]] = {name: [] for name in self._rois}

        for positions in self._track_positions:
            if positions.size < 2:
                continue
            frame = self._trajectory.iloc[positions]
            for name in self._rois:
                roi_traj = frame[frame[f"in_{name}_stable"]]
                if len(roi_traj) < 2:
                    continue

                path_distance = np.sqrt(
                    roi_traj["x_cm_smoothed"].diff() ** 2 + roi_traj["y_cm_smoothed"].diff() ** 2
                ).sum()
                start_point = roi_traj.iloc[0]
                end_point = roi_traj.iloc[-1]
                straight_dist = np.sqrt(
                    (end_point["x_cm_smoothed"] - start_point["x_cm_smoothed"]) ** 2
                    + (end_point["y_cm_smoothed"] - start_point["y_cm_smoothed"]) ** 2
                )

                if straight_dist > 0:
                    per_roi[name].append(float(path_distance / straight_dist))
                else:
                    per_roi[name].append(float(np.inf) if path_distance > 0 else 1.0)

        return {
            name: (float(np.mean(values)) if values else None) for name, values in per_roi.items()
        }

    def analyze_center_vs_periphery(self, method: str, value: float) -> dict[str, Any]:
        """Generate center and periphery ROIs and runs a full analysis on them.

        Args:
            method (str): The method to define the center zone,
                          either 'distance' (cm) or 'area_ratio' (0.0-1.0).
            value (float): The corresponding value for the method.

        Returns:
            A dictionary with analysis results for 'Center' and 'Periphery'.

        """
        from shapely.affinity import scale

        arena = self._b_analyzer.arena_polygon_cm
        if method == "distance":
            center_poly = arena.buffer(-value)
        elif method == "area_ratio":
            if not 0 < value < 1:
                raise ValueError("Area ratio must be between 0 and 1.")
            # Scale the polygon's geometry around its centroid
            center_poly = scale(arena, xfact=np.sqrt(value), yfact=np.sqrt(value))
        else:
            raise ValueError("Method must be 'distance' or 'area_ratio'.")

        if not center_poly.is_valid or center_poly.is_empty:
            raise ValueError("Could not generate a valid center zone with the given parameters.")

        periphery_poly = arena.difference(center_poly)

        # Create temporary ROIs
        center_roi = ROI(name="Center", geometry=center_poly, coordinate_space="cm")
        periphery_roi = ROI(name="Periphery", geometry=periphery_poly, coordinate_space="cm")

        # Create a temporary analyzer instance to run the analysis.
        # Tudo por PALAVRA-CHAVE: a versão anterior passava o debounce como
        # terceiro posicional, e qualquer parâmetro novo inserido antes dele
        # teria trocado o argumento em silêncio.
        temp_analyzer = ROIAnalyzer(
            behavior_analyzer=self._b_analyzer,
            rois=[center_roi, periphery_roi],
            # A REGRA de inclusão também é propagada. Sem isto, Centro e
            # Periferia rodavam sempre com o default ``bbox_intersects``, mesmo
            # num projeto configurado com ``centroid_in`` — dois números do
            # mesmo relatório respondendo a critérios diferentes.
            inclusion_rule=self._inclusion_rule,
            buffer_radius_value=self._buffer_radius_value,
            min_bbox_overlap_ratio=self._min_bbox_overlap_ratio,
            bbox_overlap_basis=self._bbox_overlap_basis,
            flutter_enter_frames=self._flutter_enter,
            flutter_exit_frames=self._flutter_exit,
            min_visit_s=self._min_visit_s,
            min_gap_s=self._min_gap_s,
            max_gap_s=self._max_gap_s,
        )

        # Gather all results
        results = {
            "time_spent": temp_analyzer.get_time_spent_in_rois(),
            "latency_first_entry": temp_analyzer.get_latency_to_first_entry(),
            "entry_counts": temp_analyzer.get_entry_counts(),
            "inter_visit_latencies": temp_analyzer.get_inter_visit_latencies(),
            "distance": temp_analyzer.get_distance_in_rois(),
            "velocity_stats": temp_analyzer.get_velocity_stats_in_rois(),
            "tortuosity": temp_analyzer.get_tortuosity_in_rois(),
            "transitions": temp_analyzer.get_roi_transitions().to_dict("index"),
        }
        return results

    @staticmethod
    def analyze_social_proximity(
        full_trajectory_df: pd.DataFrame,
        radius_cm: float,
        pixelcm_x: float,
        pixelcm_y: float,
    ) -> dict[str, Any]:
        """Perform social proximity analysis on a multi-animal trajectory DataFrame.

        Args:
            full_trajectory_df (pd.DataFrame): DataFrame with all animal tracks.
            radius_cm (float): The radius of the circular dynamic ROI.
            pixelcm_x (float): Pixel-to-cm conversion factor for x-axis.
            pixelcm_y (float): Pixel-to-cm conversion factor for y-axis.

        Returns:
            A dictionary with social metrics per animal.

        """
        if "track_id" not in full_trajectory_df.columns:
            raise ValueError("Input DataFrame must contain a 'track_id' column.")

        # Use geometric mean for radius in pixels for more accuracy
        radius_px = radius_cm * np.sqrt(pixelcm_x * pixelcm_y)

        df = full_trajectory_df.copy()
        df["track_id"] = pd.to_numeric(df["track_id"], errors="coerce")
        df = df.dropna(subset=["track_id"]).copy()
        if df.empty:
            return {"social_time_seconds": {}, "social_time_percentage": {}}
        df["track_id"] = df["track_id"].astype(int)
        df["is_in_group"] = False
        df["group_id"] = -1

        # Group by frame number to process each time step
        grouped_by_frame = df.groupby("frame")

        for frame_id, frame_df in grouped_by_frame:
            if len(frame_df) < 2:
                continue

            animals = frame_df.index
            positions = {
                idx: (r["x_center_px"], r["y_center_px"]) for idx, r in frame_df.iterrows()
            }

            # Create dynamic circular ROIs
            rois = {idx: Point(pos).buffer(radius_px) for idx, pos in positions.items()}

            # Build graph of interactions
            G = nx.Graph()
            G.add_nodes_from(animals)

            for animal1, animal2 in combinations(animals, 2):
                if rois[animal1].intersects(rois[animal2]):
                    G.add_edge(animal1, animal2)

            # Find social groups (connected components)
            social_groups = list(nx.connected_components(G))

            for group_idx, group in enumerate(social_groups):
                if len(group) > 1:
                    # Mark all animals in this group
                    member_indices = list(group)
                    df.loc[member_indices, "is_in_group"] = True
                    df.loc[member_indices, "group_id"] = f"{frame_id}-{group_idx}"

        # Calculate total time in social group for each animal
        df["dt"] = df.index.to_series().diff()  # first element remains NaN

        social_time = df[df["is_in_group"]].groupby("track_id")["dt"].sum()
        total_time = df.groupby("track_id")["dt"].sum()

        social_time_percent = (social_time / total_time * 100).fillna(0)

        results = {
            "social_time_seconds": social_time.to_dict(),
            "social_time_percentage": social_time_percent.to_dict(),
        }
        return results
