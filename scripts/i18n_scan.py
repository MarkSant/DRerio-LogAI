"""Find user-facing Portuguese string literals that still need extracting.

Read-only. Produces the worklist for a migration batch, and backs the guard test
``tests/i18n/test_no_untranslated_literals.py`` -- both use the same code so the
tool and the gate can never disagree about what counts as a violation.

Usage::

    python scripts/i18n_scan.py src/zebtrack/ui/components
    python scripts/i18n_scan.py src/zebtrack --format=count

Output is ``path:line:col<TAB>[kind]<TAB>text``, one finding per line.

What counts as a finding: a Portuguese string literal that is (a) not a
docstring, (b) not already an argument of
``_()``/``gettext()``/``lazy()``/``ngettext()``, (c) not matched by
``scripts/i18n_allowlist.txt``, (d) not a structlog event name or a logging
keyword argument -- log text is for developers and stays English/untranslated --
and (e) not on a line marked ``# i18n: not-ui``, for Portuguese that is compared
rather than displayed.

Two heuristics decide "Portuguese", reported as the finding's *kind*:

``accent``
    The literal carries a Portuguese-specific character ("Não foi possível").
    Cheap, and effectively free of false positives.

``word``
    The literal contains a word from :data:`PORTUGUESE_WORDS` -- unaccented
    Portuguese, which the accent pass cannot see ("Salvar projeto", "Gravando",
    "Nenhum video", "Aguardando sinal externo").

The ``word`` pass exists because the accent heuristic waved unaccented
Portuguese through three migration phases *and* through the ratchet built on
top of it. ``coordinators/`` was inside the ratchet from phase 2 and still
published "Aguardando sinal externo... (porta N)" as status text;
``core/recording/live_session_manager.py`` spent four batches locked in the
ratchet while pushing "Carregando detector...", "Iniciando captura..." and
"Gravando" into the very same status label as its already-translated
neighbours, so the line changed language mid-session. Neither is exotic --
both were found by hand, which is precisely the failure mode a scanner is
supposed to remove.

Together the two passes are a floor, not a ceiling: Portuguese built only from
words outside the list still slips through. Add words as they are found.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH = Path(__file__).resolve().parent / "i18n_allowlist.txt"

# Characters that only appear in Portuguese (not English) text.
PORTUGUESE_CHARS = frozenset("áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ")

# Unaccented Portuguese words, matched whole and case-insensitively.
#
# Entry rule, and it is strict: a word belongs here only if it is Portuguese
# *and* is not also an English word. That is what keeps the pass usable as a CI
# gate rather than a source of noise to be switched off. Words deliberately kept
# out for failing the second half, despite being common Portuguese:
#
#   ate .......... English past tense of "eat"
#   anterior ..... English anatomical term, and this is a zebrafish codebase
#   area, data ... identical in English
#   taxa ......... English plural of "taxon"
#   um, no, do, da English words in their own right
#   use, ignore,   English imperatives that happen to be Portuguese verb forms
#   continue,
#   pause
#   video, camera, English (or near enough) and everywhere in this codebase
#   total, normal,
#   final, index
#   cores ........ English plural of "core"; settings.py and
#                  utils/hardware_capability.py both talk about CPU cores in
#                  English. The singular "cor" carries no such clash and stays.
#
# Accented forms are already caught by PORTUGUESE_CHARS, so only the unaccented
# spelling of a word like "duração" ("duracao") needs an entry here.
PORTUGUESE_WORDS = frozenset(
    """
    abrir adicionada adicionado adicionar agora aguardando aguardar aguarde ainda
    ajustar algum alguma algumas alguns alterar altura analisando analisar andamento
    antes ao aos apagar apenas apos aplicar aquario aquarios aqui arquivo arquivos
    ativa ativado ativar ativo atual atuais atualizando atualizar avancada avancado
    aviso avisos bem bloco blocos botao botoes buscar cada calculando calcular caminho
    caminhos campo campos cancelada cancelado cancelar carregando carregar cobaia
    cobaias coluna colunas como comecar concluida concluido conectado conectar
    configuracao configuracoes configurar confirmar conectando convertendo criando
    confirme contem copiar cor criada criado criar das definida definido definir depois
    desativado desativar desconectado descricao desmarcar destino deteccao detectada
    detectado detectados detectando detectar deve devem dia dias digite disponivel
    disponiveis
    distancia dos durante duracao editar embora encerrar encontrada encontrado
    encontrados entao enviar entrada escala escolha escolher especifico esperado
    esperada erro erros essa esse esta este estao estar estado
    etapa etapas excluir executando executar exibir existe existem experimento
    experimentos exportar falha falhas falhou falta faltam fechar finalizada finalizado
    finalizando finalizar foi foram formato gerada gerado gerando gerar grafico
    graficos gravacao gravada
    gravado gravando gravar imagem imagens importar incluir informe iniciada iniciado
    iniciando iniciar inicio invalida invalido isso ja janela largura limite limites
    linha linhas lista listas mais marcada marcado marcar menos mensagem mensagens
    mesma mesmo modelo modelos mostrar mover muito muitos nada nao nas nenhum nenhuma
    nivel niveis nome nomes nos novas novo
    novos nunca obrigatoria obrigatorio ocultar onde opcional origem outra outras outro
    outros padrao padroes para parada parado parar passo pasta pastas pausado pausar
    pela
    pelo pendente permitida permitido pode podem ponto pontos por porque posicao pouco
    precisa precisam preencha primeira primeiro processada processado processando
    pronta pronto
    processar procurar progresso projeto projetos proxima proximo quadro quadros quais
    qual qualquer quando quantidade quantos que recarregar recebido registrada
    registrado reiniciar relatorio relatorios removida removido removidos remover
    removendo renderizando renomear restaurar resultado resultados rotulo rotulos
    saida salvando salvar sao
    selecao selecionada selecionado selecionados selecionar selecione sem sempre sera
    serao sessao sessoes seu seus situacao sobre somente sua suas substituir sucesso
    sujeito sujeitos tabela tambem tamanho tela tentando tentar testar tipo tipos
    testando titulo titulos todas todos tudo ultima ultimo uma usuario usuarios valida
    validando valido
    valor valores varias varios vazia vazio velocidade verificando verificar versao
    voce voltar zona zonas
    """.split()
)

# Letters only: splits "Nenhum video" and "salvar_projeto" alike into words, so
# a match is always on a whole word and "Erro" can never fire on "Error".
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# An all-lowercase token with no spaces is an identifier, not a sentence: dict
# keys, structlog fields, Parquet/XLSX column names, relative paths, and the
# ``"distancia_no_{}_cm"`` templates those column names are built from. Real
# interface text is capitalised or contains a space, so this costs no recall
# worth having and removes the bulk of the false positives the word pass would
# otherwise raise.
#
# Deliberately NOT applied to the accent pass, whose behaviour must not change:
# the ratchet is green against it today and a widened exemption there could let
# a real accented string back in unnoticed.
_IDENTIFIER_RE = re.compile(r"^[a-z0-9_.\-/{}]+$")

# Callables whose string arguments are already translated.
TRANSLATION_FUNCTIONS = frozenset({"_", "gettext", "ngettext", "lazy", "translate"})

# Callables whose string arguments are developer-facing, never user-facing.
LOGGING_FUNCTIONS = frozenset({"debug", "info", "warning", "error", "critical", "exception"})

# A file containing this marker is skipped entirely. Reserved for modules whose
# Portuguese is deliberate and permanent -- currently only the first-launch
# language chooser, which must be readable before a language has been chosen.
FILE_EXEMPT_MARKER = "i18n: file-exempt"

# A line carrying this marker is skipped. For Portuguese that is *compared*,
# never rendered: the stored spelling of a day ("sem dia"), a legacy grouping
# key ("Sem Grupo"), a prefix stripped off inherited metadata ("dia ").
#
# This exists instead of widening the allowlist because the allowlist matches by
# substring across the whole tree: an entry for "sem dia" would also silence a
# genuine label like "Videos sem dia definido", and nobody would notice. A
# marker is local to the one site, and it does not fit on the line without a
# written reason -- which is the actual review artifact.
LINE_EXEMPT_MARKER = "i18n: not-ui"


@dataclass(frozen=True)
class Finding:
    """One untranslated Portuguese literal."""

    path: Path
    line: int
    col: int
    text: str
    kind: str = "accent"

    def format(self, *, relative_to: Path | None = None) -> str:
        path = self.path
        if relative_to is not None:
            try:
                path = self.path.relative_to(relative_to)
            except ValueError:
                pass
        return f"{path.as_posix()}:{self.line}:{self.col}\t[{self.kind}]\t{self.text}"


def load_allowlist(path: Path = ALLOWLIST_PATH) -> tuple[str, ...]:
    """Read the never-translate patterns, ignoring comments and blank lines."""
    if not path.exists():
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(
        stripped for line in lines if (stripped := line.strip()) and not stripped.startswith("#")
    )


def is_portuguese(text: str) -> bool:
    """True when *text* carries a Portuguese-specific character."""
    return any(char in PORTUGUESE_CHARS for char in text)


def portuguese_words_in(text: str) -> tuple[str, ...]:
    """Return the :data:`PORTUGUESE_WORDS` *text* contains, whole-word.

    Empty for anything shaped like an identifier -- see :data:`_IDENTIFIER_RE`.
    """
    if _IDENTIFIER_RE.match(text):
        return ()
    hits = {word.lower() for word in _WORD_RE.findall(text)} & PORTUGUESE_WORDS
    return tuple(sorted(hits))


def classify(text: str) -> str | None:
    """Return the finding kind for *text*, or None when it looks English."""
    if is_portuguese(text):
        return "accent"
    if portuguese_words_in(text):
        return "word"
    return None


def is_allowlisted(text: str, allowlist: tuple[str, ...]) -> bool:
    """True when *text* matches any never-translate pattern.

    A pattern matches as a substring, so ``Grupo_`` covers ``Grupo_{group}``.
    A pattern written ``=grupo`` matches only the *whole* literal.

    Exact patterns exist because substring matching over-reaches on short common
    words. ``grupo`` -- needed for one dict key in ``GROUP_ID_FALLBACK_KEYS`` --
    silently exempted every sentence containing the word, which hid seven real
    Portuguese interface strings (two of them multi-paragraph wizard tooltips)
    from the accent pass, while the migration reported ``TOTAL: 0``.
    """
    for pattern in allowlist:
        if pattern.startswith("="):
            if text == pattern[1:]:
                return True
        elif pattern in text:
            return True
    return False


class _LiteralVisitor(ast.NodeVisitor):
    """Collect Portuguese literals, skipping the contexts that are exempt."""

    def __init__(
        self,
        path: Path,
        allowlist: tuple[str, ...],
        exempt_lines: frozenset[int] = frozenset(),
    ) -> None:
        self.path = path
        self.allowlist = allowlist
        self.exempt_lines = exempt_lines
        self.findings: list[Finding] = []
        self._exempt: set[int] = set()

    # -- exemption bookkeeping ------------------------------------------------
    def _exempt_node(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                self._exempt.add(id(child))

    def _exempt_docstring(self, node: ast.Module | ast.ClassDef | ast.FunctionDef) -> None:
        body = getattr(node, "body", None)
        if not body:
            return
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                self._exempt.add(id(first.value))

    def visit_Expr(self, node: ast.Expr) -> None:
        """Exempt every bare string statement, not just the leading docstring.

        A string that is an expression-statement is evaluated and thrown away —
        it can never reach a widget. The only reason to write one is
        documentation: PEP 258 attribute docstrings (the paragraph under an enum
        member or a class attribute) are exactly this shape, and the project
        deliberately keeps its Portuguese prose. Exempting only ``body[0]``
        reported those as untranslated interface strings.
        """
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            self._exempt.add(id(node.value))
        self.generic_visit(node)

    # -- visitors -------------------------------------------------------------
    def visit_Module(self, node: ast.Module) -> None:
        self._exempt_docstring(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._exempt_docstring(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._exempt_docstring(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._exempt_docstring(node)  # type: ignore[arg-type]
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _called_name(node.func)

        if name in TRANSLATION_FUNCTIONS:
            # Already translated: the msgid may legitimately be anything.
            for arg in node.args:
                self._exempt_node(arg)
        elif name in LOGGING_FUNCTIONS:
            # Structlog: event name plus kwargs, all developer-facing.
            self._exempt_node(node)

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, str) or id(node) in self._exempt:
            return
        if node.lineno in self.exempt_lines:
            return
        kind = classify(node.value)
        if kind is None:
            return
        if is_allowlisted(node.value, self.allowlist):
            return
        self.findings.append(
            Finding(
                path=self.path,
                line=node.lineno,
                col=node.col_offset,
                text=node.value.replace("\n", "\\n"),
                kind=kind,
            )
        )


def _called_name(func: ast.expr) -> str | None:
    """Return the bare callable name for ``f(...)`` and ``obj.f(...)``."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def scan_file(path: Path, allowlist: tuple[str, ...]) -> list[Finding]:
    """Scan one Python file."""
    source = path.read_text(encoding="utf-8")
    if FILE_EXEMPT_MARKER in source:
        return []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        print(f"{path}: skipped, syntax error: {exc}", file=sys.stderr)
        return []

    exempt_lines = frozenset(
        number
        for number, line in enumerate(source.splitlines(), start=1)
        if LINE_EXEMPT_MARKER in line
    )

    visitor = _LiteralVisitor(path, allowlist, exempt_lines)
    visitor.visit(tree)
    return visitor.findings


def scan_paths(paths: list[Path], allowlist: tuple[str, ...] | None = None) -> list[Finding]:
    """Scan files and directories, recursing into directories."""
    if allowlist is None:
        allowlist = load_allowlist()

    findings: list[Finding] = []
    for target in paths:
        if target.is_file() and target.suffix == ".py":
            findings.extend(scan_file(target, allowlist))
        elif target.is_dir():
            for python_file in sorted(target.rglob("*.py")):
                findings.extend(scan_file(python_file, allowlist))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="+", type=Path, help="Files or directories to scan")
    parser.add_argument(
        "--format",
        choices=("list", "count"),
        default="list",
        help="'list' prints every finding; 'count' prints a per-file tally.",
    )
    parser.add_argument(
        "--kind",
        choices=("all", "accent", "word"),
        default="all",
        help="Restrict to one heuristic. 'word' is the unaccented pass.",
    )
    args = parser.parse_args()

    findings = scan_paths(args.paths)
    if args.kind != "all":
        findings = [finding for finding in findings if finding.kind == args.kind]

    if args.format == "count":
        tally: dict[Path, int] = {}
        for finding in findings:
            tally[finding.path] = tally.get(finding.path, 0) + 1
        for path, count in sorted(tally.items(), key=lambda item: (-item[1], str(item[0]))):
            try:
                shown = path.relative_to(REPO_ROOT)
            except ValueError:
                shown = path
            print(f"{count:5d}  {shown.as_posix()}")
        print(f"\nTOTAL: {len(findings)} literals in {len(tally)} files")
    else:
        for finding in findings:
            print(finding.format(relative_to=REPO_ROOT))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
