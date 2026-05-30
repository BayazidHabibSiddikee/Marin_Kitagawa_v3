#!/usr/bin/env python3
# games/wordgame.py — runs as its own process
import os
import sys
import random
import time
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Suppress ALSA noise
_dn = os.open(os.devnull, os.O_WRONLY)
_se = os.dup(2)
os.dup2(_dn, 2)
try:
    import turtle as t
    from tkinter import messagebox
finally:
    os.dup2(_se, 2)
    os.close(_se)
    os.close(_dn)

import arrow
from utils.tts import speak_male as talk

WORDS = [
    "nice","want","have","need","wish","give","take","love","care","help",
    "hold","keep","know","send","make","find","feel","look","show","move",
    "live","stay","join","play","work","read","talk","hear","plan","hope",
    "deal","lead","grow","rise","fall","meet","save","open","shut","turn",
    "stop","wait","walk","jump","rest","pick","push","pull","pack","pass",
    "sign","test","call","cook","bake","wash","boil","flip","stir","pour",
    "peel","feed","lift","sort","draw","type","edit","sing","snap","film",
    "zoom","chat","mail","link","code","load","sync","view","copy","clip",
    "text","post","roll","spin","calm","kind","fair","good","fine","pure",
    "true","easy","fast","slow","soft","hard","busy","cool","warm","mild",
]


class GuessTheWordGame:
    def __init__(self):
        self.screen = t.Screen()
        self.screen.bgcolor("lavender")
        self.screen.setup(600, 500)
        t.hideturtle(); t.tracer(False); t.up()
        self.drawer = t.Turtle()
        self.drawer.hideturtle(); self.drawer.up()
        self.word = ""; self.score = 6
        self.missed = []; self.right = []; self.circles = []
        self.running = True

    def _update_title(self):
        while self.running:
            hint1 = random.choice(WORDS)
            hint2 = random.choice(WORDS)
            t.title(f"Guess the Word  |  {arrow.now().format('h:mm A')}  |  Hint: {hint1}, {hint2}")
            time.sleep(1)

    def _draw_blanks(self):
        for i in range(len(self.word)):
            self.drawer.goto(-270 + 150 * i, -200)
            self.drawer.pendown()
            self.drawer.forward(100)
            self.drawer.penup()
        t.update()

    def _create_circles(self):
        for i in range(6):
            c = t.Turtle("circle"); c.shapesize(3)
            c.color("black", "sky blue"); c.up()
            c.goto(-150 + 50 * i, 0); self.circles.append(c)
        t.update()

    def _draw_letter(self, letter, pos):
        self.drawer.goto(-270 + 150 * pos, -200)
        self.drawer.write(letter.upper(), font=("Arial", 48, "bold"))
        t.update()

    def _check_win(self):
        return all(l in self.right for l in self.word)

    def _game_loop(self):
        while True:
            inp = t.textinput("Guess the Word", "Enter a letter:")
            if inp is None:
                self.running = False
                sys.exit()
            inp = inp.lower()
            if len(inp) != 1 or not inp.isalpha():
                messagebox.showwarning("Warning", "Single letter only."); continue
            if inp in self.missed or inp in self.right:
                messagebox.showwarning("Duplicate", "Already guessed!"); continue
            if inp in self.word:
                self.right.append(inp)
                for i, l in enumerate(self.word):
                    if l == inp:
                        self._draw_letter(inp, i)
                if self._check_win():
                    self.running = False
                    messagebox.showinfo("Win!", f"You guessed '{self.word.upper()}'!")
                    talk(f"Congratulations! The word was {self.word}!")
                    break
            else:
                self.missed.append(inp)
                self.score -= 1
                t.goto(-270, 150); t.clear()
                t.write("Wrong: " + ", ".join(self.missed), font=("Arial", 16, "normal"))
                self.circles[-(6 - self.score)].hideturtle()
                t.goto(-270, 200)
                t.write(f"Attempts left: {self.score}", font=("Arial", 16, "normal"))
                t.update()
                if self.score == 0:
                    self.running = False
                    messagebox.showinfo("Game Over", f"The word was '{self.word.upper()}'.")
                    talk(f"Game over! The word was {self.word}.")
                    break

    def start(self):
        threading.Thread(target=self._update_title, daemon=True).start()
        for msg in ["Welcome to Guess The Word!", "4-letter words. 6 attempts. Good luck!"]:
            t.goto(-270, 200)
            t.write(msg, font=("Arial", 18, "bold"))
            t.update()
            time.sleep(2); t.clear()
        self.word = random.choice(WORDS)
        t.goto(-270, 200)
        t.write(f"Attempts left: {self.score}", font=("Arial", 16, "normal"))
        t.goto(-270, 150)
        t.write("Wrong guesses:", font=("Arial", 16, "normal"))
        t.update()
        self._draw_blanks(); self._create_circles()
        self._game_loop()
        self.running = False
        t.done()


if __name__ == '__main__':
    _dn = os.open(os.devnull, os.O_WRONLY)
    _se = os.dup(2)
    os.dup2(_dn, 2)
    try:
        from utils.tts import speak_male as talk
        GuessTheWordGame().start()
    finally:
        os.dup2(_se, 2)
        os.close(_se)
        os.close(_dn)
