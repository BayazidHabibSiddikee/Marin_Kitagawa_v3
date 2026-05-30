#!/usr/bin/env python3
# games/connect4_2p.py — runs as its own process
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Suppress ALSA noise
_dn = os.open(os.devnull, os.O_WRONLY)
_se = os.dup(2)
os.dup2(_dn, 2)
try:
    from turtle import *
    from tkinter import messagebox
finally:
    os.dup2(_se, 2)
    os.close(_se)
    os.close(_dn)

from time import sleep
from utils.tts import speak_male as talk


class ConnectFourTwoPlayer:
    def __init__(self):
        self.screen = Screen()
        self.screen.setup(700, 600, 10, 70)
        self.screen.bgcolor('light yellow')
        self.screen.title("Connect Four — 2 Players")
        hideturtle(); tracer(False)
        self.turn = 'red'
        self.xs = [-300, -200, -100, 0, 100, 200, 300]
        self.ys = [-250, -150, -50, 50, 150, 250]
        self.occupied = [list() for _ in range(7)]
        self.validinputs = list(range(1, 8))
        self.rounds = 1
        self.fall = Turtle(); self.fall.up(); self.fall.hideturtle()
        self._draw_board()
        self.screen.onscreenclick(self.handle_click)
        self.screen.listen()

    def _draw_board(self):
        pensize(5)
        for i in range(-250, 350, 100):
            up(); goto(i, -350); down(); goto(i, 350); up()
        pensize(1); pencolor('grey')
        for i in range(-200, 300, 100):
            up(); goto(-350, i); down(); goto(350, i); up()
        pencolor('black')
        for col, x in enumerate(range(-300, 350, 100), 1):
            up(); goto(x, 270)
            write(col, font=('Arial', 20, 'normal'))
        update()

    def _check4(self, x, y, turn, dx, dy):
        for d in (-3, -2, -1, 0):
            try:
                if all(
                    0 <= x + d * dx + i * dx < 7 and
                    0 <= y + d * dy + i * dy < 6 and
                    self.occupied[x + d * dx + i * dx][y + d * dy + i * dy] == turn
                    for i in range(4)
                ):
                    return True
            except IndexError:
                pass
        return False

    def win_game(self, col, row, turn):
        x, y = col - 1, row - 1
        return (self._check4(x, y, turn, 1, 0) or
                self._check4(x, y, turn, 0, 1) or
                self._check4(x, y, turn, 1, 1) or
                self._check4(x, y, turn, 1, -1))

    def handle_click(self, x, y):
        if not (-350 < x < 350 and -350 < y < 350):
            return
        col = int((x + 350) // 100) + 1
        if col not in self.validinputs:
            messagebox.showerror("Error", "Invalid move!")
            return
        row = len(self.occupied[col - 1]) + 1
        if row > 6:
            messagebox.showerror("Error", "Column full!")
            return
        # Animate drop
        for i in range(6, row, -1):
            self.fall.goto(self.xs[col - 1], self.ys[i - 1])
            self.fall.dot(80, self.turn); update(); sleep(0.08); self.fall.clear()
        up(); goto(self.xs[col - 1], self.ys[row - 1])
        dot(80, self.turn)
        self.occupied[col - 1].append(self.turn); update()
        if self.win_game(col, row, self.turn):
            self.validinputs = []
            messagebox.showinfo("End Game", f'Player {self.turn} wins!')
            talk(f"Player {self.turn} wins!")
            return
        if self.rounds == 42:
            messagebox.showinfo("Tie", "It's a tie!")
            talk("It's a tie!")
            return
        self.rounds += 1
        if len(self.occupied[col - 1]) == 6:
            self.validinputs.remove(col)
        self.turn = 'yellow' if self.turn == 'red' else 'red'

    def start(self):
        self.screen.mainloop()


if __name__ == '__main__':
    _dn = os.open(os.devnull, os.O_WRONLY)
    _se = os.dup(2)
    os.dup2(_dn, 2)
    try:
        from utils.tts import speak_male as talk
        ConnectFourTwoPlayer().start()
    finally:
        os.dup2(_se, 2)
        os.close(_se)
        os.close(_dn)
