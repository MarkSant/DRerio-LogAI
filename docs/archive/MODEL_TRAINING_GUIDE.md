# Guia de Treinamento de Modelos YOLO para ZebTrack-AI

## 📋 Visão Geral

Este guia documenta as convenções e melhores práticas para treinar modelos YOLO personalizados compatíveis com o ZebTrack-AI. O sistema suporta tanto modelos de **segmentação** quanto de **detecção**, com convenções específicas de nomenclatura de classes.

## 🎯 Convenções de Classes

O ZebTrack-AI espera modelos com classes específicas para funcionar corretamente:

### Modelos de Segmentação (`*_seg.pt`)

Modelos de segmentação devem ter **2 classes**:

| Classe ID | Nome Primário | Alternativas Aceitas | Descrição |
|-----------|---------------|----------------------|-----------|
| **0** | `aqua` | `aquarium`, `tank`, `agua` | Aquário/tanque de água |
| **1** | `zebrafish` | `fish`, `peixe` | Peixe zebrafish |

**Uso:**
- **Classe 0**: Utilizada na fase inicial de detecção de arena
- **Classe 1**: Utilizada para rastreamento de animais após arena definida

### Modelos de Detecção (`*_oi.pt`)

Modelos de detecção (apenas bboxes, sem segmentação) devem ter **1 classe**:

| Classe ID | Nome Primário | Alternativas Aceitas | Descrição |
|-----------|---------------|----------------------|-----------|
| **0** | `zebrafish` | `fish`, `peixe` | Peixe zebrafish |

**Nota:** Modelos de detecção não incluem detecção de aquário, apenas animais.

## 🔍 Extração Automática de Nomes

O ZebTrack-AI **extrai automaticamente** os nomes de classes dos modelos:

### Para Modelos PyTorch (`.pt`)
```python
from ultralytics import YOLO
model = YOLO("modelo.pt")
class_names = model.names  # {0: 'aqua', 1: 'zebrafish'}
```

### Para Modelos OpenVINO (após conversão)
Os nomes são salvos em `metadata.json` durante a conversão:
```json
{
  "class_names": {
    "0": "aqua",
    "1": "zebrafish"
  }
}
```

**Vantagens:**
- ✅ Não há hardcoding de nomes no código
- ✅ Modelos com nomes customizados funcionarão automaticamente
- ✅ Sistema loggará warnings se nomes não forem reconhecidos

## 📝 Arquivo de Configuração (`data.yaml`)

Ao treinar modelos personalizados no Ultralytics YOLO, use o seguinte formato de `data.yaml`:

### Para Segmentação

```yaml
path: /caminho/para/dataset
train: images/train
val: images/val
test: images/test  # opcional

# Classes
names:
  0: aqua         # ou "aquarium", "tank"
  1: zebrafish    # ou "fish", "peixe"
```

### Para Detecção

```yaml
path: /caminho/para/dataset
train: images/train
val: images/val
test: images/test  # opcional

# Classes
names:
  0: zebrafish    # ou "fish", "peixe"
```

## 🏋️ Processo de Treinamento

### 1. Preparação do Dataset

**Estrutura de Diretórios:**
```
dataset/
├── images/
│   ├── train/
│   │   ├── img001.jpg
│   │   ├── img002.jpg
│   │   └── ...
│   └── val/
│       ├── img101.jpg
│       └── ...
└── labels/
    ├── train/
    │   ├── img001.txt
    │   ├── img002.txt
    │   └── ...
    └── val/
        ├── img101.txt
        └── ...
```

**Formato de Anotações (YOLO):**
- Cada imagem tem um arquivo `.txt` correspondente
- Para segmentação: `<class_id> <x1> <y1> <x2> <y2> ... <xn> <yn>` (polígono)
- Para detecção: `<class_id> <x_center> <y_center> <width> <height>` (bbox normalizado)

### 2. Comando de Treinamento

#### Segmentação
```bash
yolo segment train \
  data=data.yaml \
  model=yolov8n-seg.pt \
  epochs=100 \
  imgsz=640 \
  batch=16 \
  name=zebrafish_seg
```

#### Detecção
```bash
yolo detect train \
  data=data.yaml \
  model=yolov8n.pt \
  epochs=100 \
  imgsz=640 \
  batch=16 \
  name=zebrafish_det
```

### 3. Exportação do Modelo

Após o treinamento, exporte o modelo:

```bash
yolo export model=runs/segment/zebrafish_seg/weights/best.pt format=torchscript
```

O arquivo `best.pt` pode ser usado diretamente no ZebTrack-AI.

## ✅ Validação de Modelos

### Inspeção no ZebTrack-AI

O sistema fornece um método de inspeção para validar modelos:

```python
from zebtrack.core.model_service import ModelService

# Após adicionar o modelo ao sistema
model_info = model_service.inspect_model("best_seg.pt")

print(f"Tipo: {model_info['model_task']}")
print(f"Classes: {model_info['class_names']}")
print(f"Número de classes: {model_info['num_classes']}")
```

**Saída Esperada:**
```
Tipo: segment
Classes: {0: 'aqua', 1: 'zebrafish'}
Número de classes: 2
```

### Validação Automática

Ao carregar um modelo, o sistema automaticamente:

1. **Verifica classes esperadas**
   - Loggará **erro** se classes obrigatórias estiverem ausentes
   - Loggará **warning** se nomes de classes forem inesperados

2. **Valida compatibilidade**
   - Modelo de segmentação deve ter 2 classes (aquário + peixe)
   - Modelo de detecção deve ter 1 classe (peixe)

3. **Aceita variações de nomes**
   - Sistema reconhece `aqua`, `aquarium`, `tank` para classe 0
   - Sistema reconhece `zebrafish`, `fish`, `peixe` para classe 1

## 🚨 Problemas Comuns

### Problema 1: "Modelo incompatível: classes ausentes [0, 1]"

**Causa:** Modelo não tem as classes esperadas.

**Solução:** Verifique o `data.yaml` usado no treinamento. Certifique-se de que as classes estão definidas corretamente:
```yaml
names:
  0: aqua
  1: zebrafish
```

### Problema 2: Nomes de classes genéricos (`class_0`, `class_1`)

**Causa:** Modelo OpenVINO sem `metadata.json`.

**Solução:** Reconverta o modelo para OpenVINO através do ZebTrack-AI. O sistema automaticamente criará o `metadata.json` com os nomes corretos.

### Problema 3: Detecções não aparecem após treinar novo modelo

**Causa:** Threshold de confiança muito alto ou modelo mal treinado.

**Solução:**
1. Ajuste o threshold de confiança no ZebTrack-AI (Configurações → Detector)
2. Valide o modelo com:
   ```bash
   yolo segment predict model=best.pt source=test_image.jpg
   ```

## 📊 Métricas de Qualidade

Após treinamento, valide a qualidade do modelo:

### Métricas Mínimas Recomendadas

| Métrica | Segmentação | Detecção |
|---------|-------------|----------|
| **mAP@0.5** | ≥ 0.90 | ≥ 0.85 |
| **mAP@0.5:0.95** | ≥ 0.70 | ≥ 0.60 |
| **Precision** | ≥ 0.90 | ≥ 0.85 |
| **Recall** | ≥ 0.85 | ≥ 0.80 |

### Testes Funcionais

Antes de usar em produção, teste o modelo:

1. **Detecção de Aquário** (seg only):
   - Modelo detecta aquário com confiança ≥ 0.8
   - Máscara cobre pelo menos 80% da área do aquário

2. **Detecção de Peixes**:
   - Modelo detecta todos os peixes visíveis
   - Bounding boxes cobrem o animal completo
   - Confiança média ≥ 0.7

3. **Rastreamento**:
   - Track IDs permanecem estáveis entre frames
   - Sem trocas de ID durante oclusões

## 🔧 Troubleshooting

### Logs de Validação

O sistema loga todas as validações. Para debugging:

```bash
tail -f logs/zebtrack.log | grep "validate_classes"
```

**Exemplos de logs:**

✅ **Sucesso:**
```
detector_service.validate_classes.success: model_path=best_seg.pt plugin_classes={0: 'aqua', 1: 'zebrafish'}
```

⚠️ **Warning (nome inesperado):**
```
detector_service.validate_classes.unexpected_name: class_id=0 actual_name='aquario' expected_names=['aqua', 'aquarium', 'tank', 'agua']
```

❌ **Erro (classe ausente):**
```
detector_service.validate_classes.missing: model_path=bad_model.pt plugin_classes={0: 'fish'} missing=[1]
```

## 📚 Recursos Adicionais

- [Ultralytics YOLO Documentation](https://docs.ultralytics.com/)
- [YOLOv8 Segmentation Guide](https://docs.ultralytics.com/tasks/segment/)
- [Custom Dataset Training](https://docs.ultralytics.com/datasets/detect/)
- [Model Export Formats](https://docs.ultralytics.com/modes/export/)

## 🔄 Atualizações Futuras

Este sistema foi projetado para ser extensível. Futuramente, o ZebTrack-AI poderá suportar:

- Múltiplas espécies de peixes
- Detecção de comportamentos específicos
- Modelos multi-classe customizados

Para solicitar novos recursos, abra uma issue no repositório do projeto.

---

**Versão:** 3.0
**Última Atualização:** 2025-01-28
**Autor:** ZebTrack-AI Development Team
