# 👻 Correção de Câmeras Fantasma (Ghost Cameras)

**Data**: 2025-11-12
**Branch**: `claude/implement-camera-live-fixes-011CV2djwZTBipDWkVTDWN37`

## 🔴 Problema Identificado

### Sintomas Reportados pelo Usuário

1. **Câmera índice 0**: Preview PRETO (sem imagem) antes das modificações
2. **Após seleção de câmera 1**: Erro "Falha ao abrir câmera 1"
3. **Segunda detecção**: Programa trava e não consegue mais detectar câmeras
4. **Nomes inconsistentes**: "Segunda câmera" mostra nome da webcam USB mas abre câmera do notebook

### Análise da Causa Raiz

O problema NÃO era de mapeamento de índices, mas sim de **câmeras fantasma** (ghost cameras):

```
WIZARD DETECTAVA:
├─ Índice 0: Câmera "fantasma" (isOpened=True, mas read() nunca retorna frames)
├─ Índice 1: Câmera do notebook (funcional)
├─ Índice 2: Webcam USB (funcional)
└─ Índice 3: Outra câmera (funcional)

PROBLEMA:
• Wizard só verificava cap.isOpened()
• Não testava se cap.read() realmente retornava frames
• Câmera índice 0 "existia" mas não capturava imagens
• Health check sem timeout travava ao tentar ler frames que nunca chegavam
```

## ✅ Correções Implementadas

### 1. Wizard: Validação de Captura de Frames

**Arquivo**: `src/zebtrack/core/wizard_service.py`

```python
# ANTES (BUGADO):
if cap.isOpened():
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    # ... adiciona câmera à lista

# DEPOIS (CORRIGIDO):
if cap.isOpened():
    # Testa captura com timeout de 2 segundos
    import threading
    test_result = {"success": False, "frame": None}

    def try_read():
        try:
            ret, frame = cap.read()
            test_result["success"] = ret
            test_result["frame"] = frame
        except Exception:
            test_result["success"] = False

    read_thread = threading.Thread(target=try_read, daemon=True)
    read_thread.start()
    read_thread.join(timeout=2.0)

    if not test_result["success"] or test_result["frame"] is None:
        log.warning("wizard_service.camera_ghost_detected", index=i)
        cap.release()
        consecutive_failures += 1
        continue

    # Só adiciona câmera se REALMENTE captura frames
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    # ...
```

**Benefício**: Câmeras fantasma (índice 0) NÃO aparecem mais na lista

### 2. LiveCameraService: Remoção de Health Check Travante

**Arquivo**: `src/zebtrack/core/live_camera_service.py`

```python
# REMOVIDO (causava travamento):
# Perform health check - try capturing 3 test frames
test_frames_captured = 0
for attempt in range(3):
    ret, frame = self.camera.get_frame()  # ← TRAVAVA AQUI
    if ret and frame is not None:
        test_frames_captured += 1
    time.sleep(0.1)
```

**Benefício**: Programa não trava mais na segunda tentativa de detecção

### 3. Resolução Forçada para 720p (mantida)

**Arquivo**: `src/zebtrack/core/live_camera_service.py`

```python
# Force 1280x720 resolution for consistent performance
temp_settings.camera.desired_width = 1280
temp_settings.camera.desired_height = 720
```

**Benefício**: Câmeras de alta resolução não causam mais lag

## 📊 Resultados Esperados

### ANTES da Correção

| Índice | Wizard Detecta? | Funciona? | Imagem |
|--------|----------------|-----------|---------|
| 0 | ✅ Sim | ❌ Não | 🖤 Preview preto |
| 1 | ✅ Sim | ✅ Sim | ✅ Câmera notebook |
| 2 | ✅ Sim | ✅ Sim | ✅ Webcam USB |
| 3 | ✅ Sim | ✅ Sim | ✅ Outra câmera |

**Problema**: Usuário selecionava "segunda câmera" (índice 1) mas wizard mostrava nomes errados

### DEPOIS da Correção

| Índice Real | Wizard Detecta? | Wizard Mostra Como | Funciona? |
|-------------|----------------|---------------------|-----------|
| 0 | ❌ **Rejeitado** | - | - |
| 1 | ✅ Sim | Primeira câmera | ✅ Sim |
| 2 | ✅ Sim | Segunda câmera | ✅ Sim |
| 3 | ✅ Sim | Terceira câmera | ✅ Sim |

**Solução**: Wizard só mostra câmeras que **realmente funcionam**

## 🧪 Como Testar

1. **Feche completamente o programa** (se estiver aberto)
2. **Abra novamente**: `poetry run zebtrack`
3. **Clique em "Detectar Câmeras"**
4. **Observe os logs**:
   ```
   wizard_service.camera_ghost_detected index=0 reason="isOpened=True but read() failed or timed out"
   wizard_service.detect_cameras.complete count=3 indices=[1, 2, 3]
   ```
5. **Selecione primeira câmera da lista** → Deve abrir câmera do notebook
6. **Selecione segunda câmera da lista** → Deve abrir webcam USB
7. **Nomes agora devem bater** com as câmeras físicas

## 🐛 Problemas Conhecidos

### Erros de Tipagem (Não Afetam Execução)

```python
# Type "dict" is not assignable to "list[dict]"
cls._camera_cache = cameras  # Line 369
```

**Status**: ⚠️ Warning apenas, não afeta funcionalidade
**Razão**: Cache mal tipado no código original
**Ação**: Pode ser ignorado ou corrigido em PR futuro

## 📝 Arquivos Modificados

- ✅ `src/zebtrack/core/wizard_service.py` - Adicionada validação de captura com timeout
- ✅ `src/zebtrack/core/live_camera_service.py` - Removido health check travante
- ✅ `CHANGELOG.md` - Documentadas as correções

## 🎯 Próximos Passos

1. **Teste com suas 4 câmeras** e confirme que índice 0 não aparece mais
2. **Verifique nomes das câmeras** na lista do wizard
3. **Reporte se ainda há alguma inconsistência**

---

**Autor**: GitHub Copilot
**Revisão Necessária**: Teste manual pelo usuário
