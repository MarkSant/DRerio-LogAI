# Modo de Gatilho Externo (Live Projects)

Como fazer o **Arduino dar a partida na gravação** em vez do operador clicar.
Use quando o início da gravação precisa coincidir com um evento externo — um
estímulo, a abertura de um portão, um botão do próprio setup, outro equipamento.

Este documento cobre o gatilho de **entrada** (Arduino → DRerio: "comece agora").
Para o sentido oposto — DRerio → Arduino, ligar um LED quando o animal entra numa
ROI — veja [`arduino-bindings.md`](arduino-bindings.md). Os dois são
independentes e podem ser usados juntos.

## Preciso disso? (resposta curta: provavelmente não)

**Não. O modo é OPT-IN e vem desligado.** Se você não marcar a caixa, nada muda:
a gravação começa quando você clica em "Iniciar", exatamente como sempre. Nenhum
Arduino é exigido, nada trava, nenhum aviso aparece.

Marcar "Usar Arduino" **também não** liga o gatilho — são duas caixas separadas.
Você pode usar o Arduino só para os comandos por zona e continuar iniciando as
gravações na mão. Ao desmarcar "Usar Arduino", o gatilho é desmarcado junto e
fica desabilitado.

## O contrato: o sketch precisa FALAR

Este é o ponto onde a maioria dos setups falha:

> **O sketch de referência que acompanha o projeto NÃO serve para o gatilho.**
> Ele só *recebe* tokens (comandos por zona) — nunca *envia* nada numérico. Se
> você ligar o gatilho e gravar com ele, a sessão vai esperar para sempre.

O DRerio escuta a serial continuamente e interpreta **linhas numéricas** vindas
do dispositivo:

| O Arduino envia | O DRerio faz |
| --------------- | ------------ |
| `1` | Inicia a gravação que está armada |
| `0` | Encerra a gravação em curso (ou desarma a espera) |
| qualquer outro número | Registra no log e ignora |
| texto (ex.: `Red LED 1 ON`) | Tratado como ACK/mensagem, **nunca** como gatilho |

A distinção número/texto é o que separa gatilho de ACK. `Serial.println(1)`
dispara a gravação; `Serial.println("1 ON")` não.

## Sketch mínimo

Um botão no pino 2 que inicia a gravação ao ser pressionado:

```cpp
const int BOTAO_INICIO = 2;
int ultimoEstado = HIGH;
unsigned long ultimoDebounce = 0;
const unsigned long DEBOUNCE_MS = 50;

void setup() {
  // INPUT_PULLUP, nunca INPUT: um pino flutuante dispara sozinho.
  pinMode(BOTAO_INICIO, INPUT_PULLUP);
  Serial.begin(9600);   // precisa bater com arduino.baud_rate
}

void loop() {
  // Nunca use delay() aqui — ele bloqueia a leitura da serial pelo tempo todo.
  int estado = digitalRead(BOTAO_INICIO);

  if (estado != ultimoEstado && (millis() - ultimoDebounce) > DEBOUNCE_MS) {
    ultimoDebounce = millis();
    if (estado == LOW) {          // pressionado (pull-up: LOW = fechado)
      Serial.println(1);          // NUMERO puro -> o DRerio grava
    }
    ultimoEstado = estado;
  }
}
```

Para encerrar por hardware, envie `Serial.println(0)` do mesmo jeito. Se você não
enviar `0`, a gravação termina normalmente pela duração configurada.

## Passo a passo

1. **No wizard** (etapa 3, "Configuração de Gravação ao Vivo"):
   - marque **"Usar Arduino para sincronização"** — a porta é detectada e
     pré-selecionada sozinha (o app prefere a que responde ao handshake e tem
     "Arduino" na descrição);
   - clique em **"Testar"** para confirmar que a porta abre;
   - marque **"Modo de Gatilho Externo (External Trigger)"**.
2. **Termine o wizard** normalmente e abra o projeto. A porta é aberta no load.
3. **Na grade de Progresso**, clique numa cobaia e em **"▶️ Iniciar"**.
   - A gravação **não** começa. Aparece o aviso
     **"Aguardando sinal externo... (porta COMx)"**.
   - As zonas são pedidas ANTES dessa espera — o polígono precisa estar pronto
     antes de ficarmos aguardando o sinal.
4. **Acione o gatilho**. Ao receber `1`, a gravação começa.

## Configuração da porta

Por máquina, em [`config.local.yaml`](../../../config.local.yaml):

```yaml
arduino:
  port: 'COM3'        # COM3 no Windows, /dev/ttyACM0 no Linux
  baud_rate: 9600     # precisa bater com o Serial.begin() do sketch
  handshake: none     # 'none' (padrão) = conectado assim que a porta abre
  ack: none           # 'none' (padrão) = não espera resposta "OK"
```

`handshake: ready_line` exige que o sketch imprima `Arduino is ready.` no boot.
Com o padrão `none`, basta a porta abrir.

## Quando a gravação é RECUSADA

Com o gatilho ligado, o DRerio prefere recusar a sessão a gravar na hora errada —
uma gravação fora de sincronia é dado inútil que só se descobre na análise.

| Situação | Mensagem | O que fazer |
| -------- | -------- | ----------- |
| Gatilho ligado, **"Usar Arduino" desligado** | "…exige um Arduino configurado" | Ligue o Arduino no projeto, ou desligue o gatilho |
| Gatilho ligado, Arduino ligado, **porta não conectada** | "…o Arduino não está conectado (porta COMx)" | Verifique o cabo e se a porta não está tomada por outro programa; reabra o projeto |

O segundo caso é comum e silencioso: se o cabo estiver solto quando você abre o
projeto, aparece um aviso de "modo offline" e o projeto abre assim mesmo. Sem
essa recusa, a sessão armaria e esperaria um sinal que não tem por onde chegar.

## Solução de problemas

| Sintoma | Causa provável |
| ------- | -------------- |
| Fica em "Aguardando sinal externo" para sempre | O sketch não envia número puro. `Serial.println("1")` com aspas é texto, não gatilho — confira no Monitor Serial da IDE |
| Nada acontece e nem o aviso aparece | O gatilho não está marcado no projeto; confira em "Config. Avançadas"/JSON do projeto |
| "Não foi possível conectar" ao abrir o projeto | Porta ocupada pelo Monitor Serial da IDE do Arduino — feche-o (só um programa por porta) |
| Dispara sozinho, sem tocar em nada | Pino do botão declarado como `INPUT` em vez de `INPUT_PULLUP` — pino flutuante oscila |
| Dispara com muito atraso | `delay()` dentro do `loop()`. Use `millis()` |
| O DRerio loga o evento mas não grava | Nenhuma sessão armada. O `1` só vale depois do "▶️ Iniciar"; antes disso é registrado e ignorado |

## Referências

- [`arduino-bindings.md`](arduino-bindings.md) — o sentido oposto (ROI → dispositivo)
- [`system_integration.md`](../../reference/system_integration.md) § 5.11 — arquitetura do gate
- `scripts/ard_sketch/Program_Final/Program_Final.ino` — sketch de referência dos
  comandos por zona (**não** implementa o gatilho; use-o como base e acrescente
  o `Serial.println(1)` acima)
