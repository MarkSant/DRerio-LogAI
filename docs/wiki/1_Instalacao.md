# Instalação e configuração

Esta página não pressupõe **nenhuma experiência** com programação, terminais ou GitHub. Todo termo
usado é explicado onde aparece pela primeira vez, e todo passo diz como saber se deu certo.

Versão em inglês: [Installation and Setup](1_Installation.md).

Se você já instalou projetos em Python antes, a versão curta é: instale o Python 3.12, baixe e
extraia o ZIP do código-fonte, dê dois cliques em `install.bat`. Todo o resto desta página é
detalhe para quando algo não sair assim.

Desenvolvedores: pule para [Instalando para desenvolver](#instalando-para-desenvolver).

## Conteúdo

- [Antes de começar](#antes-de-começar)
- [Passo 1 — Instalar o Python](#passo-1--instalar-o-python)
- [Passo 2 — Baixar o DRerio LogAI](#passo-2--baixar-o-drerio-logai)
- [Passo 3 — Extrair o ZIP num lugar permanente](#passo-3--extrair-o-zip-num-lugar-permanente)
- [Passo 4 — Rodar o instalador](#passo-4--rodar-o-instalador)
- [Passo 5 — Abrir o programa](#passo-5--abrir-o-programa)
- [E se eu precisar do terminal?](#e-se-eu-precisar-do-terminal)
- [Atualizando para uma versão nova](#atualizando-para-uma-versão-nova)
- [Se o fetch-weights disser que não existe módulo chamado zebtrack](#se-o-fetch-weights-disser-que-não-existe-módulo-chamado-zebtrack)
- [Solução de problemas](#solução-de-problemas)
- [macOS e Linux](#macos-e-linux)
- [Usando Git em vez do ZIP](#usando-git-em-vez-do-zip)
- [Instalando para desenvolver](#instalando-para-desenvolver)
- [Sobrescritas locais de configuração](#sobrescritas-locais-de-configuração)

## Antes de começar

**Veja se há espaço no computador.** A instalação precisa de cerca de **3 GB livres em disco** — a
maior parte são as bibliotecas científicas (PyTorch, OpenVINO, OpenCV) e uns 240 MB de modelos
treinados. 8 GB de RAM é o mínimo, 16 GB é confortável.

Para ver quanto espaço você tem no Windows: abra o **Explorador de Arquivos** (o ícone de pasta
amarela na barra de tarefas), clique em **Este Computador** à esquerda e leia a barra do disco C:.

**Você não precisa de placa de vídeo especial.** Nenhuma placa NVIDIA é exigida. Em máquinas Intel a
análise é acelerada pelo OpenVINO.

**Reserve de 15 a 30 minutos**, a maior parte de download sem supervisão.

## Passo 1 — Instalar o Python

**O que é o Python:** a linguagem de programação em que o DRerio LogAI foi escrito. Instalá-la
instala o motor que roda o programa. Você nunca vai precisar escrever Python.

**Qual versão:** a **3.12** (a 3.13 também serve). **A 3.14 não** — uma das bibliotecas usadas não
tem pacote pronto para ela, e a instalação falha culpando a coisa errada.

1. Abra <https://www.python.org/downloads/release/python-3129/>.
2. Role até o fim, até a tabela **Files**.
3. Clique em **Windows installer (64-bit)**. Baixa um arquivo parecido com
   `python-3.12.9-amd64.exe`.
4. Abra o arquivo baixado (costuma estar na pasta **Downloads**; o navegador também o mostra no pé
   da janela ou no ícone ⤓).
5. **Na primeira tela do instalador, marque a caixa "Add python.exe to PATH"**, lá embaixo, *antes*
   de clicar em qualquer outra coisa.

   > **Por que essa caixa importa.** "PATH" é a lista de pastas que o Windows percorre quando um
   > programa pede outro programa pelo nome. Sem a marcação, o Python fica instalado mas invisível
   > para tudo que precisa dele, e as mensagens de erro seguintes nunca mencionam o Python. Esta é
   > de longe a causa mais comum de a instalação falhar.

6. Clique em **Install Now** e espere. Ao terminar, clique em **Close**.

**Como saber que deu certo:** a última tela do instalador diz "Setup was successful". Para ter
certeza, a verificação está em [E se eu precisar do terminal?](#e-se-eu-precisar-do-terminal).

> **Este passo pode ser pulado.** O instalador do passo 4 se oferece para instalar o Python 3.12,
> se o seu computador tiver o instalador de aplicativos do próprio Windows (`winget`, presente no
> Windows 11 e no Windows 10 atualizado). Fazer você mesmo é mais previsível, por isso é o passo 1.

## Passo 2 — Baixar o DRerio LogAI

**O que é o GitHub:** o site onde ficam o código-fonte do programa e seus downloads oficiais. Você
não precisa de conta.

1. Abra a página de releases:
   <https://github.com/MarkSant/DRerio-LogAI/releases>

   Um "release" é uma versão publicada. A mais nova fica no topo, marcada como **Latest**.

2. Nesse release, procure a seção **Assets** (pode ser preciso clicar na palavra **Assets** para
   expandir).

3. Clique em **Source code (zip)**.

   > **O que é esse arquivo.** "Source code" (código-fonte) parece coisa de programador, mas é
   > simplesmente o programa completo, compactado num arquivo só. Esta é a forma normal de baixar o
   > DRerio LogAI. Não escolha `Source code (tar.gz)` — é a mesma coisa num formato que o Windows
   > não abre sozinho.
   >
   > Os arquivos `.pt` também listados em Assets são os modelos treinados. **Você não precisa
   > baixá-los à mão**; o instalador cuida disso.

O arquivo — `DRerio-LogAI-7.1.0.zip` ou parecido — cai na sua pasta **Downloads**.

## Passo 3 — Extrair o ZIP num lugar permanente

Um ZIP é uma pasta dentro de uma caixa. O Windows deixa espiar dentro sem desempacotar, e aí mora
uma armadilha: programas rodados de dentro de um ZIP se comportam mal, então é preciso extrair.

1. Abra o **Explorador de Arquivos** e vá até **Downloads**.
2. Clique com o **botão direito** no ZIP baixado e escolha **Extrair tudo...**.
3. Na caixa que aparece, troque o destino sugerido por algo curto e permanente, por exemplo:

   ```text
   C:\DRerio-LogAI
   ```

4. Clique em **Extrair** e espere.

**Escolha essa pasta com cuidado.** Ela vira a casa do programa: os modelos, as configurações, o
cache do OpenVINO e — a menos que você decida diferente — seus projetos moram dentro dela.

- **Não** use `Downloads`, que as pessoas esvaziam.
- **Evite** pastas sincronizadas por OneDrive, Google Drive ou Dropbox: elas podem travar ou baixar
  parcialmente arquivos enquanto o programa está usando.
- Evite acentos e espaços no caminho sempre que puder.

**Como saber que deu certo:** abra a pasta extraída. Você deve ver arquivos chamados `install.bat`,
`pyproject.toml`, `README.md` e uma pasta `src`. Se em vez disso houver uma única pasta de nome
comprido, entre nela — os arquivos de verdade estão um nível abaixo, e é essa pasta interna que
deve ser tratada como a casa do programa.

## Passo 4 — Rodar o instalador

1. Na pasta extraída, ache o **`install.bat`** e dê **dois cliques**.

   > O Explorador pode esconder a terminação `.bat`. Procure o arquivo chamado `install`, com ícone
   > de engrenagem ou de janelinha.

2. **O Windows pode mostrar uma caixa azul: "O Windows protegeu o computador".** Isso aparece
   porque o arquivo veio da internet, não porque haja algo errado com ele. Clique em **Mais
   informações** e depois em **Executar assim mesmo**.

3. Abre-se uma janela preta que vai contando o que faz, em quatro passos:

   ```text
   [1/4] Checking Python
   [2/4] Checking Poetry
   [3/4] Installing dependencies (this takes several minutes)
   [4/4] Downloading detector models (~250 MB)
   ```

4. **Ele pode fazer uma ou duas perguntas**, e a resposta para as duas é sim — tecle `Y` e Enter:

   - *"Install Python 3.12 now?"* — só se o passo 1 foi pulado ou não fez efeito.
   - *"Install Poetry now?"* — o **Poetry** é a ferramenta que baixa os ~1,7 GB de bibliotecas de
     que o programa precisa. O instalador o busca no site oficial e o coloca onde o Windows
     consegue encontrar, que é o trabalho que você teria de fazer à mão.

5. Espere. O passo 3 leva vários minutos e mostra pouco; o passo 4 baixa cerca de 240 MB. A janela
   termina com:

   ```text
   Setup complete.
   Start the application from the "DRerio LogAI" icon on your Desktop.
   ```

6. Tecle qualquer coisa para fechar a janela.

**Se ele parar no meio**, a última mensagem sai em amarelo e diz o que fazer. O instalador para no
primeiro passo que falha de propósito — veja [Solução de problemas](#solução-de-problemas). Depois
de resolver a causa, rode o `install.bat` de novo: ele continua de onde parou, não recomeça.

## Passo 5 — Abrir o programa

Dê dois cliques no ícone **DRerio LogAI** da área de trabalho (há um no menu Iniciar também).

Na primeira abertura, ele:

1. Pergunta o idioma. A resposta fica gravada; mude depois em **Configurações → Idioma...**.
2. Mostra uma tela de abertura enquanto mede o hardware e escolhe o jeito mais rápido de rodar os
   modelos. **Esta é a abertura mais lenta que você terá** — o resultado fica em cache.
3. Abre a janela principal e, em seguida, a janela **Primeiros passos**, explicando os modelos de
   detecção e se vale ligar o OpenVINO na sua máquina.

O que fazer em seguida: [Primeiros passos com o seu primeiro projeto](user-guide/GETTING_STARTED.md)
(em inglês).

## E se eu precisar do terminal?

A maioria das pessoas nunca precisa. Vale conhecer mesmo assim, porque instruções de diagnóstico são
escritas como comandos.

**O que é o terminal:** uma janela onde se digita comandos em vez de clicar. No Windows, o que este
projeto usa se chama **PowerShell**.

**Para abri-lo já na pasta certa** (isso importa — os comandos agem sobre a pasta em que você está):

1. Abra a pasta do programa no Explorador de Arquivos (`C:\DRerio-LogAI`).
2. Clique na barra de endereço no topo, escreva `powershell` por cima do caminho e tecle Enter.

Abre-se uma janela azul ou preta, mostrando o caminho da pasta e um sinal `>`.

**Para rodar um comando:** digite (ou cole com o botão direito) e tecle Enter. O comando terminou
quando o `>` volta. Alguns levam minutos sem imprimir nada — é normal.

Verificações úteis:

```powershell
python --version
```

Imprime algo como `Python 3.12.9`. Se não imprimir nada, abrir a Microsoft Store, ou mostrar uma
versão que comece com 3.14, esse é o problema a resolver primeiro.

```powershell
poetry run zebtrack
```

Abre o programa mostrando qualquer erro que o atalho da área de trabalho teria escondido.

```powershell
poetry run fetch-weights --check
```

Confere os modelos treinados sem baixar nada.

> **"Abra um terminal novo"** aparece em algumas instruções. Quer dizer: feche a janela e abra
> outra. O terminal lê o PATH uma única vez, ao abrir, então um programa instalado depois disso
> continua invisível para ele até lá.

## Atualizando para uma versão nova

1. Baixe e extraia o ZIP novo, como nos passos 2 e 3, numa pasta **nova**.
2. Da pasta antiga, copie para ela:
   - `config.local.yaml` — suas configurações, inclusive idioma e câmera;
   - a pasta `weights/` — para não baixar os modelos de novo;
   - as pastas de projeto que estiverem dentro da pasta do programa.
3. Dê dois cliques no `install.bat` da pasta nova.
4. Apague a pasta antiga quando a nova estiver funcionando.

**Rode o `install.bat` de novo também depois de mover a pasta.** O atalho da área de trabalho guarda
um caminho absoluto, então mover a pasta o deixa apontando para o nada. (Ele só recria o atalho;
nada é baixado outra vez.)

## Se o fetch-weights disser que não existe módulo chamado zebtrack

```text
ModuleNotFoundError: No module named 'zebtrack'
```

A mensagem nomeia o sintoma, não a causa. Ela quer dizer que a instalação não chegou a colocar o
programa em si no lugar, então os comandos dele apontam para algo que não existe. Duas coisas
produzem isso:

**O ambiente está no Python errado.** Verifique:

```powershell
poetry env info --path
poetry run python -V
```

Qualquer coisa fora de 3.12 ou 3.13 explica o problema: o NumPy fixado não publica pacote acima da
3.13, então na 3.14 a instalação tenta compilá-lo do zero, falha, e deixa o projeto desinstalado.
Refaça o ambiente na 3.12:

```powershell
poetry env use 3.12
poetry install
```

**Ou o ambiente é mais antigo que o comando.** O `fetch-weights` chegou na 7.0.0. Um ambiente criado
a partir de uma cópia anterior não tem esse comando; rodar `poetry install` de novo depois da
atualização o cria.

## Solução de problemas

| Sintoma | O que significa e o que fazer |
| --- | --- |
| O instalador diz "No supported Python found" | Falta Python, ou ele foi instalado sem "Add python.exe to PATH". Reinstale com a caixa marcada (passo 1) e rode o `install.bat` de novo |
| Ele diz que o Poetry não pôde ser instalado | Em geral é falta de internet, ou um proxy/firewall bloqueando `install.python-poetry.org`. Tente em outra conexão, ou instale o Poetry à mão: <https://python-poetry.org/docs/#installation> |
| `poetry install` falhou | Nada aqui precisa de compilador. As causas usuais são queda de conexão ou pouco espaço livre (~1,7 GB). Resolva e rode o `install.bat` de novo |
| "O Windows protegeu o computador" | O arquivo veio da internet. **Mais informações → Executar assim mesmo** |
| Dois cliques em `install.ps1` abrem o Bloco de Notas | É o esperado — o Windows não executa `.ps1` com dois cliques. Use o `install.bat`, que existe exatamente por isso |
| O ícone da área de trabalho não faz nada | A pasta foi movida ou renomeada. Rode o `install.bat`, ou `scripts\install_shortcut.ps1`. Veja `logs/analysis.log` |
| O programa abre mas se recusa a rastrear | Faltam os modelos: `poetry run fetch-weights` |
| `ModuleNotFoundError: No module named 'zebtrack'` | [Veja acima](#se-o-fetch-weights-disser-que-não-existe-módulo-chamado-zebtrack) |
| A análise está muito lenta | Ligue o OpenVINO em **Configurações → Definições de modelo...** e converta os pesos que usa; aumente o intervalo de análise |
| O assistente não aparece | Apague o `config.local.yaml`, ou defina `ui_features.use_wizard_for_project_creation: true` |

Mais: [Solução de problemas](user-guide/TROUBLESHOOTING.md) · [FAQ](3_FAQ.md).

## macOS e Linux

### Debian / Ubuntu

```bash
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
./setup.sh
```

O `setup.sh` instala os pacotes de sistema (inclusive as ligações do Tk), o Poetry via pipx, as
dependências Python e os modelos, e cria um atalho `.desktop`. Opções: `--skip-weights`,
`--skip-launcher`.

Em outras distribuições, instale Python 3.12, `python3.12-tk` (ou equivalente) e
[Poetry](https://python-poetry.org/docs/#installation), e siga os comandos de macOS abaixo.

### macOS

```bash
brew install python@3.12        # ou o instalador do python.org
curl -sSL https://install.python-poetry.org | python3 -
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
poetry install
poetry run fetch-weights
poetry run zebtrack
```

A janela do Tkinter aparece no Dock. Ainda não há script de atalho para macOS; abra com
`poetry run zebtrack`.

## Usando Git em vez do ZIP

O **Git** é uma ferramenta que baixa o código e o mantém atualizável com um comando. É opcional — o
ZIP entrega exatamente os mesmos arquivos — mas, se você pretende atualizar com frequência, poupa a
cópia descrita em [Atualizando](#atualizando-para-uma-versão-nova).

Instale-o em <https://git-scm.com/download/win> (aceite todos os padrões) e, num terminal:

```powershell
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
powershell -ExecutionPolicy Bypass -File install.ps1
```

Para atualizar depois:

```powershell
git pull
powershell -ExecutionPolicy Bypass -File install.ps1
```

## Instalando para desenvolver

Os mesmos passos com o grupo de dependências de desenvolvimento, e sem atalho:

```powershell
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
poetry install --with dev
poetry run pre-commit install
poetry run fetch-weights
poetry run pytest -q
```

`install.ps1 -Dev` faz tudo isso no Windows, mais o atalho. Outras opções: `-SkipWeights`,
`-SkipShortcut`, `-Yes` (aceita toda oferta de instalar pré-requisito, para execuções
desassistidas).

**Sobre os pesos.** Os modelos YOLO treinados não ficam no repositório por causa do tamanho. O
`fetch-weights` baixa os seis do release nomeado em `weights_manifest.json` e confere cada arquivo
contra um SHA-256 registrado; um download interrompido ou corrompido é descartado, não guardado
pela metade. O `--check` valida uma instalação existente sem baixar.

Quatro dos seis são os especialistas por perspectiva (`seg` e `det`, lateral e de cima) e já vêm
como padrão. Os outros dois — `best_oi.pt` e `best_seg.pt` — são generalistas de 3 classes, com uma
classe `zup-aqua` que os especialistas não têm; eles são registrados por
`WeightManager.discover_weights()` e aparecem no painel de modelos, mas não ocupam papel nenhum por
conta própria. (Antes da v7.1.0 ficavam atrás de uma opção `--all` e não casavam com nenhum padrão
de descoberta, então eram invisíveis mesmo depois de baixados. A opção continua aceita e hoje não
muda nada.)

### Gerenciando o atalho

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1            # criar ou reparar
powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1 -NoDesktop # só menu Iniciar
powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1 -Remove    # apagar
```

O atalho aponta para `.venv\Scripts\pythonw.exe -m zebtrack`: `pythonw` para não deixar um console
atrás da janela (fechar esse console mataria uma análise em curso), e `-m zebtrack` porque o script
de console que o Poetry gera reintroduz um. O diagnóstico vai para `logs/analysis.log`
independentemente de como o programa foi aberto.

O script se recusa a criar um atalho cujo ambiente não consegue importar o `zebtrack`, de modo que
uma instalação quebrada é reportada agora, e não como uma janela que abre e some.

## Sobrescritas locais de configuração

**Não há passo de configuração aqui.** O `config.local.yaml` é criado na primeira execução —
responder à pergunta de idioma é o que o escreve — e o que um operador precisa está todo na
interface:

| Configuração | Onde se escolhe |
| --- | --- |
| Idioma da interface | **Configurações → Idioma...** |
| Modelos, papéis, OpenVINO | **Configurações → Definições de modelo...** |
| Câmera | Assistente de projeto (projetos ao vivo); depois, no diálogo de detalhe da sessão |
| Porta do Arduino | O painel do Arduino, que lista as portas que encontra |
| Limiares do detector, regra de ROI | O passo de modelos do assistente, o editor de configurações e o painel de análise |

**Câmera e porta do Arduino moram no projeto, e o valor do projeto vence.** O `ProjectInitializer` lê
`project_data["arduino_port"]` primeiro e só então recorre a `settings.arduino.port`, então
defini-los globalmente à mão não tem efeito num projeto que tem os seus — que é todo projeto criado
pelo assistente. Use o arquivo global para um padrão realmente da máquina, não para configurar um
estudo.

Para sobrescrever algo que a interface não expõe, escreva no arquivo *apenas* as chaves que está
mudando:

```yaml
ui_features:
  use_wizard_for_project_creation: true # padrão
```

> **Não** copie o `config.yaml` inteiro para dentro dele. Os dois são mesclados recursivamente, então
> uma cópia completa congela todos os padrões atuais nesta máquina e esconde silenciosamente toda
> correção futura.

Outras sobrescritas (limiares do detector, barramento de eventos) estão documentadas em
`docs/reference/operational_reference.md` e `docs/guides/developer/wizard.md`.
