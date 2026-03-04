int leds[4]    = {2, 3, 4, 5};
int buttons[4] = {7, 8, 9, 11};
const int buzzerPin = 12;

const int MAX_SEQ = 12;
int sequenceArr[MAX_SEQ];

const int MAX_MISTAKES = 2;

struct SpeedProfile {
  int stepOnMs;
  int stepOffMs;
};

SpeedProfile SPEED_SLOW       = {360, 260};
SpeedProfile SPEED_FAST       = {150,  90};
SpeedProfile SPEED_SOUND_SLOW = {320, 240};

// ===== Frequency mapping for passive buzzer =====
int freqForButton(int btnIdx) {
  switch (btnIdx) {
    case 0: return 400;
    case 1: return 550;
    case 2: return 690;
    case 3: return 940;
    default: return 400;
  }
}

// ===== Signals =====
void successSignal() {
  int melody[] = {659, 784, 988};
  int durations[] = {80, 80, 150};
  for (int i = 0; i < 3; i++) {
    tone(buzzerPin, melody[i]);
    digitalWrite(leds[i], HIGH);
    delay(durations[i]);
    noTone(buzzerPin);
    digitalWrite(leds[i], LOW);
    delay(30);
  }
}

void loseSignal() {
  int melody[] = {784, 740, 698, 659, 622, 587, 523, 494, 440};
  int durations[] = {120, 120, 120, 120, 120, 140, 180, 180, 300};
  for (int i = 0; i < 9; i++) {
    tone(buzzerPin, melody[i]);
    delay(durations[i]);
    noTone(buzzerPin);
    delay(30);
  }
  delay(200);
  tone(buzzerPin, 220);
  delay(300);
  noTone(buzzerPin);
}

void winSignal() {
  int melody[] = {523, 659, 784, 1047, 988, 1047, 1319};
  int durations[] = {120, 120, 120, 200, 120, 160, 350};
  for (int i = 0; i < 7; i++) {
    tone(buzzerPin, melody[i]);
    delay(durations[i]);
    noTone(buzzerPin);
    delay(40);
  }
  for (int r = 0; r < 3; r++) {
    for (int i = 0; i < 4; i++) digitalWrite(leds[i], HIGH);
    delay(120);
    for (int i = 0; i < 4; i++) digitalWrite(leds[i], LOW);
    delay(120);
  }
}

// ===== Input =====
int waitButtonPress() {
  while (true) {
    for (int i = 0; i < 4; i++) {
      if (digitalRead(buttons[i]) == LOW) {
        delay(20);
        if (digitalRead(buttons[i]) == LOW) {
          while (digitalRead(buttons[i]) == LOW) {}
          delay(20);
          return i;
        }
      }
    }
  }
}

void generateSequence(int length) {
  for (int i = 0; i < length; i++) sequenceArr[i] = random(0, 4);
}

// mode: 0=Visual+Sound, 1=VisualOnly, 2=SoundOnly
void playStep(int btnIdx, int mode, const SpeedProfile &spd) {
  int f = freqForButton(btnIdx);

  if (mode == 0) { // Visual + Sound
    digitalWrite(leds[btnIdx], HIGH);
    tone(buzzerPin, f);
    delay(spd.stepOnMs);
    noTone(buzzerPin);
    digitalWrite(leds[btnIdx], LOW);
    delay(spd.stepOffMs);
  } else if (mode == 1) { // Visual only
    digitalWrite(leds[btnIdx], HIGH);
    delay(spd.stepOnMs);
    digitalWrite(leds[btnIdx], LOW);
    delay(spd.stepOffMs);
  } else { // Sound only
    tone(buzzerPin, f);
    delay(spd.stepOnMs);
    noTone(buzzerPin);
    delay(spd.stepOffMs);
  }
}

void playSequence(int length, int mode, const SpeedProfile &spd) {
  for (int i = 0; i < length; i++) playStep(sequenceArr[i], mode, spd);
}

bool getPlayerInput(int length, int mode) {
  for (int i = 0; i < length; i++) {
    int pressed = waitButtonPress();

    digitalWrite(leds[pressed], HIGH);
    if (mode != 1) { // beep feedback only in sound modes
      tone(buzzerPin, freqForButton(pressed));
      delay(120);
      noTone(buzzerPin);
    } else {
      delay(120);
    }
    digitalWrite(leds[pressed], LOW);

    if (pressed != sequenceArr[i]) return false;
  }
  return true;
}

// ===== 7-try config =====
void getTryConfig(int tryNumber, int &mode, const SpeedProfile* &spd, int &length) {
  if (tryNumber >= 1 && tryNumber <= 3) {
    mode = 0;               // Visual + Sound
    spd = &SPEED_SLOW;
    length = 3 + tryNumber; // 4,5,6
    return;
  }
  if (tryNumber >= 4 && tryNumber <= 6) {
    mode = 1;               // Visual only
    spd = &SPEED_FAST;
    length = tryNumber; // 4,5,6
    return;
  }
  else if(tryNumber == 7){
  // Try 7: Sound-only, length 5
  mode = 2;
  spd = &SPEED_SLOW;
  length = 3;
  }
  else{
    mode = 2;
    spd = &SPEED_SLOW;
    length = 3;
  }

}

// ===== Serial command: wait for START =====
bool waitForStartCommand() {
  static String buf = "";
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      buf.trim();
      if (buf == "START") {
        buf = "";
        return true;
      }
      buf = "";
    } else {
      buf += c;
      if (buf.length() > 32) buf = "";
    }
  }
  return false;
}

void setup() {
  Serial.begin(9600);

  for (int i = 0; i < 4; i++) {
    pinMode(leds[i], OUTPUT);
    pinMode(buttons[i], INPUT_PULLUP);
  }
  pinMode(buzzerPin, OUTPUT);
  noTone(buzzerPin);

  randomSeed(analogRead(A0));

  Serial.println("READY"); // Python can wait for this if needed
}

void loop() {
  // idle until Python sends START
  if (!waitForStartCommand()) {
    delay(10);
    return;
  }

  int mistakes = 0;

  for (int t = 1; t <= 8; t++) {
    int mode, length;
    const SpeedProfile* spd;
    getTryConfig(t, mode, spd, length);

    generateSequence(length);

    delay(400);
    playSequence(length, mode, *spd);

    bool ok = getPlayerInput(length, mode);

    if (ok) {
      Serial.println("TRY_PASS");
      successSignal();
    } else {
      Serial.println("TRY_FAIL");
      mistakes++;
      loseSignal();
      if (mistakes >= MAX_MISTAKES) {
        Serial.println("GAME_OVER");
        return; // back to waiting for START
      }
    }

    delay(500);
  }

  // Completed all 7 tries with <= 1 fail
  Serial.println("GAME_WIN");
  winSignal();
  return; // back to waiting for START
}