#!/usr/bin/env python3
# games/connect4_ai.py — runs as its own process
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
from copy import deepcopy
from random import choice
from utils.tts import speak_male as talk


class ConnectFour:
    def __init__(self):
        self.screen = Screen()
        self.screen.setup(700, 600, 10, 70)
        self.screen.bgcolor("light yellow")
        self.screen.title("Connect Four — vs Computer")
        hideturtle()
        tracer(False)
        pensize(5)
        self.xs = [-300, -200, -100, 0, 100, 200, 300]
        self.ys = [-250, -150, -50, 50, 150, 250]
        self.turn = "red"
        self.occupied = [list() for _ in range(7)]
        self.validinputs = list(range(1, 8))
        self.rounds = 1
        self.fall = Turtle("circle")
        self.fall.hideturtle()
        self.fall.up()
        self._draw_board()
        self.screen.onscreenclick(self.handle_click)
        self.screen.listen()

    def _draw_board(self):
        for i in range(-250, 350, 100):
            up(); goto(i, -350); down(); goto(i, 350); up()
        pensize(1); pencolor("grey")
        for i in range(-200, 300, 100):
            up(); goto(-350, i); down(); goto(350, i); up()
        pencolor("black")
        for col, x in enumerate(range(-300, 350, 100), 1):
            up(); goto(x, 270)
            write(col, align="center", font=("Arial", 20, "bold"))
        update()

    def _check4(self, occupied, x, y, color, dx, dy):
        for d in (-3, -2, -1, 0):
            try:
                if all(
                    0 <= x + d * dx + i * dx < 7 and
                    0 <= y + d * dy + i * dy < 6 and
                    occupied[x + d * dx + i * dx][y + d * dy + i * dy] == color
                    for i in range(4)
                ):
                    return True
            except IndexError:
                pass
        return False

    def win_game(self, col, row, color, board):
        x, y = col - 1, row - 1
        return (self._check4(board, x, y, color, 1, 0) or
                self._check4(board, x, y, color, 0, 1) or
                self._check4(board, x, y, color, 1, 1) or
                self._check4(board, x, y, color, 1, -1))

    def computer_best_move(self):
        if len(self.occupied[3]) == 0:
            return 4
        if len(self.validinputs) == 1:
            return self.validinputs[0]
        for move in self.validinputs:
            test = deepcopy(self.occupied)
            test[move - 1].append(self.turn)
            if self.win_game(move, len(test[move - 1]), self.turn, test):
                return move
        loser = []
        opp = "yellow" if self.turn == "red" else "red"
        for m in self.validinputs:
            test = deepcopy(self.occupied)
            test[m - 1].append(opp)
            if self.win_game(m, len(test[m - 1]), opp, test):
                loser.append(m)
        safe = [m for m in self.validinputs if m not in loser]
        return choice(safe) if safe else choice(self.validinputs)

    def make_move(self, col, is_computer=False):
        if col not in self.validinputs:
            return
        row = len(self.occupied[col - 1]) + 1
        for i in range(6, row, -1):
            self.fall.goto(self.xs[col - 1], self.ys[i - 1])
            self.fall.dot(80, self.turn)
            update(); sleep(0.08); self.fall.clear()
        up(); goto(self.xs[col - 1], self.ys[row - 1])
        dot(80, self.turn); update()
        self.occupied[col - 1].append(self.turn)
        if self.win_game(col, row, self.turn, self.occupied):
            self.validinputs.clear()
            winner = "Computer" if is_computer else "Player"
            messagebox.showinfo("Game Over", f"{winner} ({self.turn}) wins!")
            talk(f"Game over! {winner} wins!")
            sys.exit(0)
        if self.rounds == 42:
            messagebox.showinfo("Game Over", "It's a draw!")
            talk("Game over! It's a draw!")
            sys.exit(0)
        if len(self.occupied[col - 1]) == 6:
            self.validinputs.remove(col)
        self.turn = "yellow" if self.turn == "red" else "red"
        self.rounds += 1

    def handle_click(self, x, y):
        if not (-350 < x < 350 and -350 < y < 350):
            return
        col = int((x + 350) // 100) + 1
        if col not in self.validinputs:
            messagebox.showinfo("Invalid", "Column full!")
            return
        self.make_move(col, is_computer=False)
        if self.validinputs:
            sleep(0.5)
            self.make_move(self.computer_best_move(), is_computer=True)

    def start(self):
        self.screen.mainloop()


if __name__ == '__main__':
    _dn = os.open(os.devnull, os.O_WRONLY)
    _se = os.dup(2)
    os.dup2(_dn, 2)
    try:
        from utils.tts import speak_male as talk
        ConnectFour().start()
    finally:
        os.dup2(_se, 2)
        os.close(_se)
        os.close(_dn)
