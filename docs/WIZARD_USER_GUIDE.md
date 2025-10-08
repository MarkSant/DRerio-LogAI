# Wizard de Criação de Projetos - Guia do Usuário

**Versão:** 1.6
**Última Atualização:** 2025-10-08

## Visão Geral

O Wizard de Criação de Projetos é um assistente inteligente de 5 etapas que automatiza a criação de projetos no ZebTrack-AI. Desde a versão 1.6 ele é a experiência padrão (a flag `ui_features.use_wizard_for_project_creation` deve permanecer habilitada). Ele detecta automaticamente o design experimental, importa zonas de arquivos Parquet existentes e configura estratégias de processamento otimizadas para cada vídeo.

### Benefícios

- ✅ **Detecção Automática de Design**: Identifica grupos, dias e estrutura experimental
- ✅ **Importação Inteligente de Parquets**: Reaproveita arenas, ROIs e trajetórias já processadas
- ✅ **Configuração Granular**: Controle individual por vídeo do que importar
- ✅ **Economia de Tempo**: Evita reprocessamento desnecessário
- ✅ **Validação Inteligente**: Previne erros antes da criação do projeto

## As 5 Etapas

### Etapa 1: Descoberta - Entendendo Seu Contexto

**Objetivo:** Definir o tipo de projeto e intenções de importação.

#### Configurações:

**1.1 Tipo de Projeto**

- **Experimental**: Para estudos com grupos de tratamento, controles, design temporal
  - Exemplo: Comparar efeito de drogas em grupos Control vs Treatment ao longo de 5 dias

- **Exploratório**: Para análises abertas, testes rápidos, projetos sem design formal
  - Exemplo: Testar configuração de câmera, validar parâmetros de detecção

**1.2 Organização de Pastas** (somente para projetos experimentais)

- **Não tenho estrutura de pastas**: Todos os vídeos estão numa pasta única
- **Pastas = Design Experimental**: Pastas representam grupos/dias (ex: `/Control/Day01/`)
- **Pastas = Organização**: Pastas são apenas organizacionais, sem significado experimental

**1.3 Arquivos Parquet Existentes**

- **Não possuo arquivos Parquet**: Processar tudo do zero
- **Importar somente zonas** (arena + ROIs): Gerar apenas trajetórias
- **Importar tudo disponível**: Usar todos os dados existentes

💡 **Dica**: Se você já processou vídeos antes, selecione a importação de Parquets para economizar tempo!

---

### Etapa 2: Seleção de Arquivos

**Objetivo:** Selecionar os vídeos e/ou pastas para o projeto.

#### Opções de Seleção:

**2.1 Adicionar Vídeos Individuais**
- Clique em "Adicionar Vídeos..."
- Selecione arquivos `.mp4`, `.avi`, ou `.mov`
- Suporta seleção múltipla (Ctrl+Click ou Shift+Click)

**2.2 Adicionar Pastas**
- Clique em "Adicionar Pasta..."
- Selecione pasta raiz contendo vídeos
- Scan recursivo: encontra vídeos em subpastas automaticamente

**2.3 Remover Seleções**
- Selecione item na lista
- Clique em "Remover Selecionado"

#### Exemplo de Estrutura:

```
Experimento_Canabidiol/
├── Control/
│   ├── Day01/
│   │   ├── Subject01.mp4
│   │   └── Subject02.mp4
│   └── Day02/
│       └── Subject01.mp4
└── Treatment/
    ├── Day01/
    │   └── Subject01.mp4
    └── Day02/
        └── Subject02.mp4
```

💡 **Dica**: Para projetos com estrutura de pastas, use "Adicionar Pasta..." na raiz - o wizard detectará o design automaticamente!

---

### Etapa 3: Detecção Automática

**Objetivo:** Analisar vídeos e detectar design experimental automaticamente.

#### O que é Detectado:

**3.1 Design Experimental** (somente projetos experimentais)
- **Grupos**: Control, Treatment, Dose_Low, Dose_High, etc.
- **Dias**: Day01, Day02, D1, D2, etc.
- **Sujeitos**: Subject01, S01, Fish_01, etc.
- **Confiança**: Percentual de certeza da detecção (0-100%)

**3.2 Análise de Parquets**
- **Arena**: `*_arena.parquet` (coordenadas do tanque)
- **ROIs**: `*_rois.parquet` (regiões de interesse)
- **Trajetória**: `*_trajectory.parquet` (dados de rastreamento)
- **Status por Vídeo**: Quais arquivos existem para cada vídeo

#### Padrões de Detecção:

1. **Grupos como Pastas**: `/Control/Day01/video.mp4`
2. **Dias como Pastas**: `/Day01/Control/video.mp4`
3. **Pastas Mistas**: `/Control_Day01/video.mp4`
4. **Baseado em Nome**: `Control_Day01_Subject01.mp4`

💡 **Dica**: A confiança de detecção indica a consistência do padrão. Valores acima de 70% são confiáveis.

---

### Etapa 4: Configuração de Importação

**Objetivo:** Definir estratégia de processamento individual para cada vídeo.

#### Padrões Inteligentes Pré-Configurados:

O wizard aplica automaticamente uma configuração inicial baseada em suas escolhas da Etapa 1:

| Escolha na Etapa 1         | Vídeo com Arena | Vídeo com ROIs | Vídeo com Trajetória | Ação Sugerida     |
|----------------------------|-----------------|----------------|----------------------|-------------------|
| Importar tudo disponível   | ✅              | ✅             | ✅                   | **SKIP** (dados completos) |
| Importar tudo disponível   | ✅              | ✅             | ❌                   | **IMPORT_ZONES** (rastrear) |
| Importar tudo disponível   | ✅              | ❌             | ❌                   | **PARTIAL** (importar arena) |
| Importar somente zonas     | ✅              | ✅             | ❌/✅                | **IMPORT_ZONES** (rastrear) |
| Não importar Parquets      | ❌/✅           | ❌/✅          | ❌/✅                | **FULL** (do zero) |

#### Opções de Importação (por vídeo):

**Colunas Interativas:**
- **Arena**: ✅ Importar coordenadas do tanque de `*_arena.parquet`
- **ROIs**: ✅ Importar regiões de interesse de `*_rois.parquet`
- **Trajetória**: ✅ Importar dados de rastreamento de `*_trajectory.parquet`

**Ação Derivada Automaticamente:**
- **SKIP**: Todos os dados existem - pular processamento
- **IMPORT_ZONES**: Importar arena + ROIs, gerar nova trajetória
- **PARTIAL**: Importar somente arena
- **FULL**: Processar tudo do zero (sem importação)

#### Como Personalizar:

1. **Duplo-clique** na célula da tabela para alternar ✅ ⟷ ❌
2. A coluna "Ação" atualiza automaticamente
3. Resumo no rodapé mostra contagem por ação

💡 **Dica**: Use SKIP para vídeos já processados e IMPORT_ZONES para reaproveitar zonas desenhadas!

---

### Etapa 5: Confirmação

**Objetivo:** Revisar todas as configurações e criar o projeto.

#### Informações Exibidas:

**5.1 Resumo do Design**
- Tipo de projeto (Experimental / Exploratório)
- Grupos detectados e confiança
- Total de vídeos selecionados

**5.2 Plano de Processamento**
- Quantidade de vídeos por ação (SKIP, IMPORT_ZONES, PARTIAL, FULL)
- Estimativa de tempo (5 minutos por vídeo a processar)

**5.3 Parquets Existentes**
- Total de arquivos arena, ROIs, trajetória, completos

**5.4 Estratégia de ROIs**
- Como resolver conflitos entre ROIs existentes e novos (Substituir / Mesclar / Manual)

#### Configurações Finais:

**Nome do Projeto**
- Gerado automaticamente com base no design detectado
- Editável manualmente
- Regras: Somente letras, números, espaços, `_` e `-`

**Localização**
- Padrão: `Documentos`
- Clique em "Procurar..." para alterar
- Validação: Pasta deve existir e ter permissão de escrita

#### Validações Finais:

✅ Nome do projeto não pode estar vazio
✅ Nome não pode conter caracteres especiais (`@`, `#`, `$`, `/`, etc.)
✅ Localização deve existir e ser acessível
✅ Não pode existir projeto com mesmo nome na localização
✅ Pelo menos 1 vídeo deve estar selecionado

💡 **Dica**: Revise cuidadosamente todas as configurações - não será possível alterar após criar o projeto!

---

## Fluxo Recomendado por Cenário

### Cenário 1: Projeto Novo (sem Parquets)

1. **Etapa 1**: Experimental + Pastas = Design Experimental + Não possuo Parquets
2. **Etapa 2**: Adicionar Pasta... (raiz do experimento)
3. **Etapa 3**: Verificar design detectado (grupos e dias)
4. **Etapa 4**: Todos os vídeos em FULL (processar do zero)
5. **Etapa 5**: Confirmar e criar

**Resultado**: Projeto criado com design detectado, todos os vídeos serão processados.

---

### Cenário 2: Importar Zonas de Projeto Anterior

1. **Etapa 1**: Experimental + Pastas = Design Experimental + **Importar somente zonas**
2. **Etapa 2**: Adicionar vídeos com `*_arena.parquet` e `*_rois.parquet` adjacentes
3. **Etapa 3**: Wizard detecta arenas e ROIs existentes
4. **Etapa 4**: Vídeos com arena+ROIs → **IMPORT_ZONES** (rastrear novamente)
5. **Etapa 5**: Confirmar

**Resultado**: Arena e ROIs importadas, novas trajetórias geradas sem redesenhar zonas.

---

### Cenário 3: Reaproveitar Processamento Completo

1. **Etapa 1**: Experimental + **Importar tudo disponível**
2. **Etapa 2**: Adicionar vídeos com `*_trajectory.parquet` adjacentes
3. **Etapa 3**: Wizard detecta dados completos
4. **Etapa 4**: Vídeos completos → **SKIP**, novos vídeos → **FULL**
5. **Etapa 5**: Confirmar

**Resultado**: Vídeos já processados são pulados, apenas novos são processados.

---

### Cenário 4: Projeto Exploratório Rápido

1. **Etapa 1**: **Exploratório** + Não possuo Parquets
2. **Etapa 2**: Adicionar 1-2 vídeos de teste
3. **Etapa 3**: Sem detecção de design (exploratory não detecta)
4. **Etapa 4**: FULL para todos
5. **Etapa 5**: Nome automático "Projeto_Exploratorio_20251004"

**Resultado**: Projeto simples criado rapidamente para testes.

---

## Perguntas Frequentes

### 1. O que acontece se eu não tiver estrutura de pastas?

O wizard funcionará normalmente, mas não detectará design automaticamente. Você poderá configurar manualmente as ações por vídeo na Etapa 4.

### 2. Posso editar a detecção de design?

Na versão 1.6, a detecção é automática e não editável. Se a confiança for baixa (<70%), considere reorganizar pastas ou renomear arquivos para seguir um dos 4 padrões suportados.

### 3. O que é a "confiança" de detecção?

É um percentual calculado com base em:
- **Consistência** do padrão (50%)
- **Cobertura** dos vídeos (30%)
- **Ausência de outliers** (20%)

Valores acima de 70% são confiáveis.

### 4. Posso voltar para etapas anteriores?

Sim! Use o botão "< Voltar" a qualquer momento. Seus dados serão preservados.

### 5. Posso cancelar o wizard?

Sim. Clique em "Cancelar" a qualquer momento. O wizard pedirá confirmação se você já tiver preenchido dados.

### 6. O que acontece se eu escolher SKIP mas o vídeo não tiver todos os dados?

O wizard não permite SKIP sem dados completos. A validação na Etapa 4 garante que SKIP só seja aplicado a vídeos com arena + ROIs + trajetória.

### 7. Quanto tempo demora o processamento?

Estimativa: **~5 minutos por vídeo** para processamento FULL. IMPORT_ZONES é mais rápido (~2-3 min). SKIP é instantâneo.

### 8. Os arquivos Parquet devem estar na mesma pasta que os vídeos?

Sim. O wizard busca arquivos com padrão `{video_name}_arena.parquet`, `{video_name}_rois.parquet`, `{video_name}_trajectory.parquet` na mesma pasta do vídeo correspondente.

Exemplo:
```
/Videos/
├── Subject01.mp4
├── Subject01_arena.parquet
├── Subject01_rois.parquet
└── Subject01_trajectory.parquet
```

---

## Solução de Problemas

### Problema: "Nenhum design detectado" mesmo com estrutura de pastas

**Causa**: Estrutura não segue um dos 4 padrões suportados.

**Solução**:
1. Verifique se pastas/nomes seguem padrões consistentes
2. Use palavras-chave reconhecidas: Control, Treatment, Day, D, Subject, S
3. Considere reorganizar pastas ou usar projeto Exploratório

---

### Problema: Wizard não encontra arquivos Parquet existentes

**Causa**: Arquivos não seguem convenção de nomenclatura.

**Solução**:
1. Renomeie Parquets para `{video_name}_arena.parquet`, etc.
2. Certifique-se de que estão na mesma pasta do vídeo
3. Verifique extensão: `.parquet` (não `.pq` ou `.parq`)

---

### Problema: Confiança de detecção muito baixa (<50%)

**Causa**: Inconsistência na estrutura de pastas/nomes.

**Solução**:
1. Revise estrutura e identifique outliers (vídeos fora do padrão)
2. Renomeie pastas/arquivos para seguir padrão consistente
3. Ou use projeto Exploratório e configure manualmente

---

### Problema: "Projeto já existe" ao criar

**Causa**: Já existe pasta com mesmo nome na localização.

**Solução**:
1. Escolha nome diferente
2. Ou selecione localização diferente
3. Ou remova/renomeie projeto existente

---

## Atalhos de Teclado

| Atalho       | Ação                            |
|--------------|---------------------------------|
| `Enter`      | Avançar para próxima etapa      |
| `Esc`        | Cancelar wizard                 |
| `Alt+V`      | Voltar para etapa anterior      |
| `Alt+P`      | Próxima etapa                   |
| `Ctrl+A`     | Adicionar vídeos (Etapa 2)      |
| `Ctrl+F`     | Adicionar pasta (Etapa 2)       |
| `Delete`     | Remover seleção (Etapa 2)       |

---

## Glossário

- **Arena**: Coordenadas do tanque de experimentação
- **ROI**: Região de Interesse (zones dentro do tanque)
- **Trajetória**: Dados de rastreamento (posições dos animais ao longo do tempo)
- **Parquet**: Formato de arquivo colunar usado para armazenar dados de tracking
- **SKIP**: Pular processamento (dados completos já existem)
- **IMPORT_ZONES**: Importar arena e ROIs, gerar nova trajetória
- **PARTIAL**: Importar somente arena
- **FULL**: Processar tudo do zero (sem importação)
- **Design Experimental**: Estrutura formal do experimento (grupos, dias, sujeitos)
- **Confiança de Detecção**: Percentual de certeza na detecção automática de design

---

## Suporte

Para reportar problemas ou sugerir melhorias:
- GitHub Issues: https://github.com/anthropics/zebtrack-ai/issues
- Documentação técnica: `docs/WIZARD_PROJECT_CREATION.md`
- Arquitetura: `docs/ARCHITECTURE.md`

---

**Versão do Wizard:** 1.6
**Schema Version:** 1
**Última Atualização:** 2025-10-04
