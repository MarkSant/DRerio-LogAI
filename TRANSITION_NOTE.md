# Nota de Transição: ZebTrack-AI → DRerio LogAI

## Contexto da Mudança

Durante o desenvolvimento inicial deste projeto, o nome de trabalho era **"ZebTrack-AI"**. No entanto, o nome oficial e definitivo do produto foi estabelecido posteriormente como **"DRerio LogAI"**.

Esta transição reflete melhor a identidade do projeto:
- **DRerio**: Referência ao modelo animal *Danio rerio* (zebrafish)
- **Log**: Registro/análise de dados comportamentais
- **AI**: Inteligência artificial para rastreamento automatizado

## Mapa de Nomenclaturas

Para evitar confusão, aqui está o mapeamento completo dos nomes utilizados:

| Contexto | Nome Utilizado | Observações |
|----------|----------------|-------------|
| **Nome do Produto** | DRerio LogAI | Nome oficial apresentado aos usuários |
| **Repositório GitHub** | ZebTrack-AI | Mantido para preservar histórico e links existentes |
| **Pacote Python (PyPI)** | `drerio-logai` | Nome público para instalação (`pip install drerio-logai`) |
| **Pacote Interno** | `zebtrack` | Nome do módulo Python (`import zebtrack`) - mantido por compatibilidade |
| **Comando CLI** | `zebtrack` | Comando de terminal (`poetry run zebtrack`) - mantido por conveniência |

## Justificativa Técnica

### Por que manter nomes diferentes?

1. **Repositório (`ZebTrack-AI`)**:
   - GitHub redireciona automaticamente URLs antigas quando repositórios são renomeados
   - Manter o nome preserva histórico do Git e links externos
   - Mudança desnecessária para infraestrutura de CI/CD

2. **Pacote Interno (`zebtrack`)**:
   - Refatorar o nome do pacote interno exigiria mudanças massivas no código
   - Afetaria todos os imports: `from zebtrack.core import ...`
   - Alto risco vs. baixo benefício (usuários não veem o nome interno)

3. **Nome Público (`drerio-logai`)**:
   - Reflete a identidade correta do produto no PyPI
   - Primeira impressão do usuário ao descobrir o projeto
   - Facilita buscas relacionadas a "Danio rerio" e "zebrafish"

## Estratégia de Documentação

Esta abordagem de nomenclatura mista é comum em engenharia de software:

| Exemplo Real | Nome Público | Pacote Python | Observação |
|--------------|--------------|---------------|------------|
| OpenCV | opencv-python | `cv2` | Tradição histórica |
| Pillow | Pillow | `PIL` | Fork do PIL original |
| **DRerio LogAI** | drerio-logai | `zebtrack` | Nome definido após desenvolvimento |

## Impacto para Usuários

### Usuários Finais
- Veem apenas **"DRerio LogAI"** na interface, documentação e janela "Sobre"
- Não precisam se preocupar com nomes internos

### Desenvolvedores
- Importam como `import zebtrack` (consistente com toda a base de código)
- Instalam via `poetry install` ou `pip install drerio-logai` (quando publicado)
- Executam via `poetry run zebtrack` (comando CLI mantido por conveniência)

## Checklist de Atualização

✅ **Completo**:
- [x] Interface gráfica (títulos, logos, menu "Sobre")
- [x] pyproject.toml (nome público e descrição)
- [x] README.md (logo, descrição, nota explicativa)
- [x] CLAUDE.md (instruções para IA)
- [x] Esta nota de transição (TRANSITION_NOTE.md)

⏳ **Futuro** (se necessário):
- [ ] Documentação da Wiki
- [ ] Issues e pull requests antigos (atualizar descrições conforme relevância)
- [ ] Screenshots do aplicativo

## Conclusão

A coexistência de nomes reflete diferentes contextos de uso e prioriza a experiência do usuário final (que vê "DRerio LogAI") sobre consistência técnica interna. Esta é uma prática de engenharia aceitável e comum na comunidade Python.

Para mais informações, consulte:
- `pyproject.toml` - Configuração do pacote
- `CLAUDE.md` - Overview da arquitetura
- `README.md` - Introdução ao projeto
