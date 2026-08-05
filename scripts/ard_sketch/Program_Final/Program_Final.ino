/*
  Sketch de referencia DRerio LogAI — comandos por zona (closed-loop).

  Protocolo: o software envia "<numero>\n" e o firmware responde uma linha de
  texto (ACK). O ACK e' usado pelo DRerio para medir a latencia frame->acao
  (arquivo 5_ClosedLoop_*.csv).

  REGRA DE OURO: o loop() NUNCA pode bloquear. Todo delay() no loop atrasa a
  leitura da serial na mesma medida — os comandos ficam represados no buffer e
  depois sao drenados todos de uma vez, o que faz um par ENTRAR/SAIR colapsar
  num piscar de milissegundos (invisivel) e a latencia medida explodir.
  Por isso as temporizacoes abaixo usam millis(), nunca delay().

  Mapa de tokens (deve bater com os bindings por zona configurados no DRerio):
    1 = LED verm. 1 ON    2 = LED verm. 1 OFF
    3 = LED azul   ON     4 = LED azul   OFF
    5 = LED verde  ON     6 = LED verde  OFF
    7 = LED verm. 2 ON    8 = LED verm. 2 OFF
  Cada zona deve usar um PAR proprio (ex.: Z1=1/2, Z2=3/4, Z3=5/6, Z4=7/8).
  Reaproveitar um numero como "entrada" de uma zona e "saida" de outra faz o
  dispositivo ficar aceso — o DRerio avisa sobre isso na aba de Zonas.
*/

int redLED1 = 13;
int redLED2 = 12;
int greenLED = 11;
int blueLED = 10;

int botaoChoque = 7;
int pinStepUpON = 6;
int stateBotaoChoque;

int botaoFlash = 4;
int pinFlash = 3;

int stateBlink = LOW;
int stateBotaoFlash;
int lastStateBotaoFlash = HIGH;
unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 5;

// --- Flash nao-bloqueante (era delay(100) + delay(100)) ---
const unsigned long FLASH_HALF_PERIOD_MS = 100;
unsigned long lastFlashToggle = 0;
int flashLevel = LOW;

// --- Choque nao-bloqueante (era delay(15000)) ---
const unsigned long CHOQUE_DURACAO_MS = 15000;
bool choqueAtivo = false;
unsigned long choqueInicio = 0;
int lastStateBotaoChoque = HIGH;

void setup() {
  pinMode(redLED1, OUTPUT);
  pinMode(redLED2, OUTPUT);
  pinMode(greenLED, OUTPUT);
  pinMode(blueLED, OUTPUT);
  Serial.begin(9600);
  // Timeout curto para Serial.parseInt(): o protocolo é "<numero>\n" escrito
  // de uma vez só pelo software. O padrão do Arduino é esperar até 1000 ms
  // por mais bytes antes de desistir de um número parcial; 50 ms já é
  // folgado para uma escrita local via USB.
  Serial.setTimeout(50);

  pinMode(pinFlash, OUTPUT);
  pinMode(botaoFlash, INPUT_PULLUP);

  // INPUT_PULLUP, nao INPUT: sem o pull-up interno o pino fica flutuando e
  // le LOW sozinho, disparando o choque (e, na versao antiga, um delay de 15 s)
  // sem ninguem apertar o botao. O botao deve ligar o pino ao GND.
  pinMode(botaoChoque, INPUT_PULLUP);
  pinMode(pinStepUpON, OUTPUT);
  digitalWrite(pinStepUpON, LOW);
}

// Drena TODOS os comandos de zona (entrada/saída de ROI) já disponíveis
// nesta passada do loop, não só um — evita que uma rajada de comandos
// fique acumulando fila e trave o LED de uma zona em "aceso".
void processarComandosSerial() {
  while (Serial.available() > 0) {
    // Descarta separadores pendentes ("\r", "\n", espaco) ANTES de chamar
    // parseInt(). Sem isso, o "\n" que sobra faz parseInt() esperar o timeout
    // e devolver 0, gerando um "Unknown command" fantasma que desalinha a
    // correlacao FIFO comando<->ACK do log de latencia.
    int proximo = Serial.peek();
    if (proximo == '\r' || proximo == '\n' || proximo == ' ' || proximo == '\t') {
      Serial.read();
      continue;
    }

    int boxNumber = Serial.parseInt();

    switch(boxNumber) {
      case 1:
        digitalWrite(redLED1, HIGH);
        Serial.println("Red LED 1 ON");
        break;
      case 2:
        digitalWrite(redLED1, LOW);
        Serial.println("Red LED 1 OFF");
        break;
      case 3:
        digitalWrite(blueLED, HIGH);
        Serial.println("Blue LED ON");
        break;
      case 4:
        digitalWrite(blueLED, LOW);
        Serial.println("Blue LED OFF");
        break;
      case 5:
        digitalWrite(greenLED, HIGH);
        Serial.println("Green LED ON");
        break;
      case 6:
        digitalWrite(greenLED, LOW);
        Serial.println("Green LED OFF");
        break;
      case 7:
        digitalWrite(redLED2, HIGH);
        Serial.println("Red LED 2 ON");
        break;
      case 8:
        digitalWrite(redLED2, LOW);
        Serial.println("Red LED 2 OFF");
        break;
      default:
        Serial.println("Unknown command");
        break;
    }
  }
}

// Botao de flash: alterna stateBlink na borda de descida (INPUT_PULLUP -> o
// botao pressionado le LOW), com debounce por millis().
void atualizarBotaoFlash() {
  int reading = digitalRead(botaoFlash);

  if (reading != lastStateBotaoFlash) {
    lastDebounceTime = millis();
  }
  if ((millis() - lastDebounceTime) > debounceDelay) {
    if (reading != stateBotaoFlash) {
      stateBotaoFlash = reading;
      if (stateBotaoFlash == LOW) {
        stateBlink = !stateBlink;
      }
    }
  }
  lastStateBotaoFlash = reading;
}

// Pisca o flash sem bloquear: inverte o nivel a cada FLASH_HALF_PERIOD_MS.
void atualizarFlash() {
  if (stateBlink != LOW) {
    if (flashLevel != LOW) {
      flashLevel = LOW;
      digitalWrite(pinFlash, LOW);
    }
    return;
  }

  if (millis() - lastFlashToggle >= FLASH_HALF_PERIOD_MS) {
    lastFlashToggle = millis();
    flashLevel = (flashLevel == LOW) ? HIGH : LOW;
    digitalWrite(pinFlash, flashLevel);
  }
}

// Choque de 15 s temporizado por millis(): dispara na borda de descida do
// botao e desliga sozinho quando a janela expira, sem travar o loop.
void atualizarChoque() {
  stateBotaoChoque = digitalRead(botaoChoque);

  if (!choqueAtivo && stateBotaoChoque == LOW && lastStateBotaoChoque == HIGH) {
    choqueAtivo = true;
    choqueInicio = millis();
    digitalWrite(pinStepUpON, HIGH);
  }

  if (choqueAtivo && (millis() - choqueInicio >= CHOQUE_DURACAO_MS)) {
    choqueAtivo = false;
    digitalWrite(pinStepUpON, LOW);
  }

  lastStateBotaoChoque = stateBotaoChoque;
}

void loop() {
  // A serial vem primeiro e o loop e' livre de delay(): o pior caso de latencia
  // passa a ser uma passada do loop (microssegundos), nao os 15 s do choque.
  processarComandosSerial();
  atualizarBotaoFlash();
  atualizarFlash();
  atualizarChoque();
}
