
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
int lastStateBotaoFlash = LOW;
long lastDebounceTime = 0;
long debounceDelay = 5;



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

  pinMode(botaoChoque, INPUT);
  pinMode(pinStepUpON, OUTPUT);
  digitalWrite(pinStepUpON, LOW);
}

void loop() {
  int reading = digitalRead(botaoFlash);
  stateBotaoChoque = digitalRead(botaoChoque);

  // Drena TODOS os comandos de zona (entrada/saída de ROI) já disponíveis
  // nesta passada do loop, não só um — evita que uma rajada de comandos
  // fique acumulando fila e trave o LED de uma zona em "aceso".
  while (Serial.available() > 0) {
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

  if (reading != lastStateBotaoFlash) {
    lastDebounceTime = millis();
      if(stateBotaoFlash == LOW) {
         stateBlink = !stateBlink;
        }
  }
  if ((millis() - lastDebounceTime) > debounceDelay) {
    stateBotaoFlash = reading;
  }
  if(stateBlink == LOW){

    digitalWrite(pinFlash, HIGH);
    delay(100);
    digitalWrite(pinFlash, LOW);
    delay(100);
  }
  lastStateBotaoFlash = reading;


  if (stateBotaoChoque == LOW) {
    digitalWrite (pinStepUpON, HIGH);
    delay (15000);
    digitalWrite (pinStepUpON, LOW);
  }

}
