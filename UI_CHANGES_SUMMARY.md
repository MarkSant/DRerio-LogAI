## UI Changes Summary

This document shows the new UI elements that were added to both dialogs.

### SingleVideoConfigDialog - New UI Section

**Before:**
- Calibração section (aquarium dimensions)
- Parâmetros de Análise section (behavior analysis)

**After:**
- Calibração section (aquarium dimensions)  
- Parâmetros de Análise section (behavior analysis)
- **NEW:** Intervalos de Processamento section:
  - "Intervalo de Análise (frames):" [text input] (default: 10)
  - "Intervalo de Exibição (frames):" [text input] (default: 10)

### CreateProjectDialog - New UI Fields

**Before:**
```
Nome do Projeto: [input]
Pasta do Projeto: [input] [Browse...]
Número de Aquários: [input]
Animais por Aquário: [input] 
Largura do Aquário (cm): [input]
Altura do Aquário (cm): [input]
Tipo de Projeto: (•) Pré-gravado ( ) Ao Vivo
```

**After:**
```
Nome do Projeto: [input]
Pasta do Projeto: [input] [Browse...]
Número de Aquários: [input]
Animais por Aquário: [input]
Largura do Aquário (cm): [input]
Altura do Aquário (cm): [input]
Intervalo de Análise (frames): [input] (default: 10)    <-- NEW
Intervalo de Exibição (frames): [input] (default: 10)   <-- NEW
Tipo de Projeto: (•) Pré-gravado ( ) Ao Vivo
```

### Functional Impact

1. **Analysis Interval**: Controls how often frames are processed for animal detection
   - Value of 10 = process every 10th frame (default behavior)
   - Value of 5 = process every 5th frame (more frequent analysis)
   - Value of 20 = process every 20th frame (less frequent analysis)

2. **Display Interval**: Controls how often processed frames are shown in the GUI during analysis
   - Value of 10 = update display every 10th processed frame (default)
   - Value of 1 = update display every processed frame (more frequent updates)
   - Value of 30 = update display every 30th processed frame (less frequent updates)

3. **Validation**: Both values must be positive integers, otherwise an error message is shown.

4. **Data Flow**: 
   - Single Video: Values passed to controller → `_process_videos()` → used directly
   - Project Creation: Values stored in project_data → loaded during batch processing

The changes maintain full backward compatibility while giving users control over processing performance and visual feedback frequency.