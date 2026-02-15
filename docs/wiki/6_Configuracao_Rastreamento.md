# Guia de Configuração de Rastreamento

Este guia descreve como ajustar os parâmetros de rastreamento para obter os melhores resultados em seus experimentos.

## 1. Seleção do Rastreador

O ZebTrack-AI oferece duas opções:

- **ByteTrack (Recomendado)**: Usa inteligência artificial e Filtro de Kalman para prever o movimento do animal. É excelente para lidar com sumiços temporários ou reflexos.
- **Rastreador Simples (Híbrido)**: Baseado apenas em distância e sobreposição de caixas. Ideal para casos muito simples (1 animal por aquário) em computadores com pouco processamento.

## 2. Parâmetros de Detecção (YOLO)

- **Confiança Mínima**: Define quão "certeza" a IA deve ter para dizer que encontrou um peixe.
  - _Exemplo_: Se o peixe está sendo ignorado, diminua para 0.15. Se o brilho da água é confundido com peixe, aumente para 0.40.
- **Limiar NMS**: Controla a sobreposição de caixas.
  - _Exemplo_: Se um único peixe aparece com duas caixas sobre ele, aumente este valor.

## 3. Parâmetros Avançados (ByteTrack)

- **Track Threshold**: Confiança mínima para manter o rastro ativo.
- **Match Threshold**: Tolerância para ligar o peixe do frame anterior ao peixe do frame atual. Para Zebrafish (que são rápidos), valores altos como **0.95** são ideais.
- **Track Buffer**: Memória do sistema. Quantos frames o sistema espera o peixe reaparecer antes de dar um novo ID.
  - _Sugestão_: Para vídeos com muitos reflexos, aumente para 150 frames.
- **Distância Máxima**: Quantos pixels o peixe pode "viajar" entre um frame processado e outro.
  - _Sugestão_: Se você processa apenas 1 a cada 10 frames, aumente para 600 ou 800.
- **IoU Threshold**: Limite de sobreposição. Como peixes são pequenos, geralmente não há sobreposição entre frames pulados; deixe em **0.05**.

## 4. Onde Ajustar

Você encontrará estas opções no **Assistente de Criação de Projeto** (etapa de Modelos) ou no menu de **Calibração** (ícone de engrenagem) para ajustes em tempo real.
