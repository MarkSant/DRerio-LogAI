# Correção de Jitter na Velocidade Angular – Resumo Técnico

## Problema Diagnosticado

Foi identificado um problema clássico de **amplificação de ruído em vetores de deslocamento de baixa magnitude** que causava a detecção espúria de milhares de "guinadas bruscas" mesmo quando o animal estava praticamente imóvel.

### Causa Raiz

1. **Jitter do Detector**: Algoritmos de detecção (YOLO, etc.) não identificam o centróide do animal exatamente no mesmo pixel a cada frame, resultando em flutuações de 1-2 pixels mesmo quando o sujeito está parado.

2. **Amplificação do Ruído**: O cálculo de `atan2(dy, dx)` é extremamente sensível quando os vetores `(dx, dy)` têm magnitude muito pequena. A direção desses vetores passa a ser dominada pelo ruído de detecção, não pelo movimento real.

3. **Resultado**: Velocidade angular espúria de centenas de graus/segundo em trajetórias quase estacionárias, gerando contagens absurdas de guinadas bruscas.

## Solução Implementada

Foi adotada uma **abordagem combinada robusta** com três camadas de proteção configuráveis:

### 1. Limiar de Movimento Mínimo (Principal)
- **Parâmetro**: `min_displacement_threshold_cm` (padrão: 0.5 cm)
- **Comportamento**: Descarta cálculos de ângulo quando o deslocamento entre posições consecutivas é menor que o limiar
- **Resultado**: Atribui `NaN` para indicar "sem movimento significativo", evitando poluição dos dados
- **Valores Típicos**: 0.3-1.0 cm dependendo da resolução do vídeo e precisão do detector

### 2. Janela de Cálculo Adaptativa (Complementar)
- **Parâmetro**: `angle_calculation_window` (padrão: 1 = frames consecutivos)
- **Comportamento**: Calcula ângulos usando frames não-consecutivos (ex: F-3, F, F+3 com window=3)
- **Resultado**: Cria vetores de deslocamento mais longos que diluem o efeito do jitter
- **Trade-off**: Reduz resolução temporal mas aumenta robustez
- **Valores Típicos**: 1-5 (usar 2-5 para detecções muito ruidosas)

### 3. Suavização Secundária (Opcional)
- **Parâmetro**: `angular_velocity_smoothing_window` (padrão: 3)
- **Comportamento**: Aplica média móvel centrada nas velocidades angulares calculadas
- **Resultado**: Reduz ruído de alta frequência sem sobre-suavizar guinadas genuínas
- **Desabilitação**: Valor 1 desativa a suavização
- **Valores Típicos**: 3-5 (valores maiores podem mascarar guinadas rápidas reais)

## Alterações no Código

### 1. `settings.py`
- Nova classe `AngularVelocitySettings` com três parâmetros configuráveis
- Validação de que `angular_velocity_smoothing_window` deve ser ímpar ou 1
- Integrada ao modelo `Settings` principal

### 2. `config.yaml`
- Seção `angular_velocity` com documentação inline dos três parâmetros
- Valores padrão conservadores mas eficazes

### 3. `behavior.py` – `BehavioralAnalyzer.__init__`
- Adicionados 3 novos parâmetros opcionais ao construtor
- Valores padrão mantêm comportamento robusto out-of-the-box

### 4. `behavior.py` – `get_angular_velocity`
- Reescrita completa do algoritmo de cálculo
- Loop manual sobre frames aplicando limiar de deslocamento
- Cálculo baseado em dois vetores (entrada e saída) ao invés de diferença de ângulos
- Suavização opcional com `rolling().mean()` centralizado
- Documentação extensa com explicação do problema de jitter

### 5. `analysis_service.py`
- Carrega configurações de `settings.angular_velocity`
- Passa parâmetros ao instanciar `ConcreteBehavioralAnalyzer`

## Testes

### Novos Testes (`test_angular_velocity_jitter.py`)
Bateria de 6 testes validando cada aspecto da solução:

1. **test_stationary_trajectory_with_low_threshold**: Trajetória estacionária com jitter deve retornar >70% NaN
2. **test_stationary_trajectory_with_permissive_threshold**: Limiar permissivo calcula valores (porém ruidosos)
3. **test_moving_phases_preserve_angular_velocity**: Movimento genuíno não é filtrado
4. **test_wider_calculation_window_reduces_noise**: Janela mais ampla reduz variância
5. **test_smoothing_reduces_variance**: Suavização reduz ruído residual
6. **test_sharp_turns_count_with_jitter_filtering**: Guinadas espúrias dramaticamente reduzidas

### Testes Legacy Atualizados
- `test_concrete_behavioral_analyzer.py`: Expectativas ajustadas para novo algoritmo
- `test_reporter_and_new_features.py`: Limiares de detecção adaptados

## Resultados Esperados

### Antes da Correção (Problema)
```
Trajetória quase estacionária (jitter de 1-2 px):
- Guinadas bruscas detectadas: ~500-1000
- Velocidade angular máxima: ~300-500 deg/s (espúria)
```

### Depois da Correção (Solução)
```
Trajetória quase estacionária (mesmo jitter):
- Guinadas bruscas detectadas: 0-5 (ruído residual mínimo)
- Velocidade angular: ~70% valores NaN, restante <50 deg/s
- Movimentos genuínos preservados
```

## Configuração e Ajuste Fino

### Para Sistemas com Alta Precisão de Detecção
```yaml
angular_velocity:
  min_displacement_threshold_cm: 0.3  # Mais sensível
  angle_calculation_window: 1          # Máxima resolução temporal
  angular_velocity_smoothing_window: 1 # Sem suavização extra
```

### Para Sistemas com Detecção Ruidosa
```yaml
angular_velocity:
  min_displacement_threshold_cm: 0.8  # Mais restritivo
  angle_calculation_window: 3          # Vetores mais longos
  angular_velocity_smoothing_window: 5 # Suavização agressiva
```

### Para Análise Exploratória (Diagnóstico)
```yaml
angular_velocity:
  min_displacement_threshold_cm: 0.1  # Muito permissivo
  angle_calculation_window: 1
  angular_velocity_smoothing_window: 1
```
Compare os resultados com e sem filtragem para quantificar o impacto do jitter.

## Retrocompatibilidade

- **Totalmente retrocompatível**: Valores padrão oferecem comportamento robusto
- **Opt-out**: Definir `min_displacement_threshold_cm: 0.0` desabilita o filtro (comportamento similar ao antigo)
- **Testes existentes**: Atualizados para refletir novo comportamento, todos passando

## Referências Técnicas

Esta solução implementa técnicas padrão para tratamento de ruído em sistemas de tracking:

1. **Dead-band Filtering**: Limiar de movimento mínimo é um filtro dead-band clássico
2. **Temporal Averaging**: Janela de cálculo adaptativa é uma forma de averaging temporal
3. **Moving Average Smoothing**: Suavização secundária usa média móvel centrada para evitar phase shift

A combinação dessas três técnicas oferece robustez extrema contra jitter sem perda significativa de informação sobre movimentos reais.

## Autoria

**Data**: 14 de Outubro de 2025  
**Contexto**: Análise comportamental de zebrafish com tracking multi-animal (ZebTrack-AI)  
**Impacto**: Correção crítica para métricas de velocidade angular e contagem de guinadas

---

### Próximos Passos Sugeridos

1. **Validação Empírica**: Testar com dados reais de experimentos e ajustar limiares conforme necessário
2. **Documentação de Usuário**: Adicionar seção no `REFERENCE_GUIDE.md` explicando quando/como ajustar os parâmetros
3. **Visualização**: Considerar adicionar gráficos comparativos (antes/depois) nos relatórios gerados
4. **Calibração Automática**: Implementar heurística para estimar limiar ideal baseado no desvio padrão do jitter observado
