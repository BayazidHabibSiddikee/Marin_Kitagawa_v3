#!/usr/bin/env python3
# tiktaktoe.py — Pure game engine, AI (O) vs User (X) on Tkinter/Turtle board
# No LLM calls, no character prompts - just game logic
import random
import sys
from pathlib import Path
from turtle import *
from tkinter import messagebox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TikTakToe:
    """Pure Tic Tac Toe game engine with simple AI."""
    
    WIN_COMBOS = [
        ['1','2','3'], ['4','5','6'], ['7','8','9'],
        ['1','4','7'], ['2','5','8'], ['3','6','9'],
        ['1','5','9'], ['3','5','7'],
    ]

    def __init__(self):
        self.cell_center = {
            '1': (-200, 200), '2': (0, 200),   '3': (200, 200),
            '4': (-200, 0),   '5': (0, 0),     '6': (200, 0),
            '7': (-200, -200),'8': (0, -200),  '9': (200, -200),
        }
        self.board = {k: None for k in self.cell_center}
        self.user_mark = 'X'
        self.system_mark = 'O'
        self.turn = 'system'
        self.round = 0
        self.available = list(self.cell_center.keys())
        self.game_over = False
        self._last_state = None

    def get_board_state(self) -> dict:
        """Return game state for external integration with marin.py"""
        rows = []
        for r in range(3):
            line = []
            for c in range(3):
                cell = str(r * 3 + c + 1)
                mark = self.board[cell]
                line.append(mark if mark else cell)
            rows.append(' | '.join(line))
        
        winner = None
        if self.game_over:
            for combo in self.WIN_COMBOS:
                marks = [self.board[c] for c in combo]
                if marks[0] and marks[0] == marks[1] == marks[2]:
                    winner = "O" if marks[0] == self.system_mark else "X"
                    break
            if not winner and self.round == 9:
                winner = "tie"
        
        return {
            "board_display": f"{rows[0]}\n---------\n{rows[1]}\n---------\n{rows[2]}",
            "available": list(self.available),
            "turn": self.turn,
            "round": self.round,
            "game_over": self.game_over,
            "winner": winner,
        }

    def draw_board(self):
        Screen()
        setup(600, 600, 10, 70)
        tracer(False)
        title("Tic Tac Toe — AI (O) vs You (X)")
        bgcolor('light pink')
        hideturtle()
        pensize(5)
        for i in (-100, 100):
            up(); goto(300, i); down(); goto(-300, i); up()
            up(); goto(i, -300); down(); goto(i, 300); up()
        for cell, center in self.cell_center.items():
            goto(center)
            write(cell, align='center', font=('Arial', 30, 'italic'))
        update()

    def draw_mark(self, cell, mark):
        x, y = self.cell_center[cell]
        goto(x, y - 40)
        color('blue' if mark == 'X' else 'red')
        write(mark, align='center', font=('Arial', 80, 'bold'))
        color('black')
        update()

    def _check_winner(self, mark):
        return any(all(self.board[c] == mark for c in combo) for combo in self.WIN_COMBOS)

    def _finish(self, msg):
        self.turn = None
        self.available = []
        self.game_over = True
        self._last_state = self.get_board_state()
        messagebox.showinfo("Game Over", msg)

    def make_move(self, cell, mark):
        self.round += 1
        self.available.remove(cell)
        self.board[cell] = mark
        self.draw_mark(cell, mark)
        self._last_state = self.get_board_state()
        
        if self._check_winner(mark):
            winner = "AI" if mark == self.system_mark else "You"
            self._finish(f"{winner} win{'s' if winner=='AI' else ''}!")
        elif self.round == 9:
            self._finish("It's a tie!")
        else:
            self.turn = "user" if mark == self.system_mark else "system"

    def _get_ai_move(self):
        """Win > Block > Center > Corner > Edge"""
        available = self.available
        if not available:
            return None

        for cell in available:
            self.board[cell] = self.system_mark
            if self._check_winner(self.system_mark):
                self.board[cell] = None
                return cell
            self.board[cell] = None

        for cell in available:
            self.board[cell] = self.user_mark
            if self._check_winner(self.user_mark):
                self.board[cell] = None
                return cell
            self.board[cell] = None

        if '5' in available:
            return '5'

        corners = [c for c in ['1', '3', '7', '9'] if c in available]
        if corners:
            return random.choice(corners)

        edges = [c for c in ['2', '4', '6', '8'] if c in available]
        return random.choice(edges) if edges else random.choice(available)

    def system_move(self):
        if not self.available or self.turn != "system":
            return
        cell = self._get_ai_move()
        if cell:
            self.make_move(cell, self.system_mark)

    def user_move(self, x, y):
        if self.turn != "user":
            return
        if not (-300 < x < 300 and -300 < y < 300):
            return
        col = int((x + 300) // 200) + 1
        row = int((y + 300) // 200) + 1
        cell = str((3 - row) * 3 + col)
        if cell not in self.available:
            messagebox.showerror("Invalid Move", "Cell already occupied!")
            return
        self.make_move(cell, self.user_mark)
        if self.available and self.turn == "system":
            ontimer(400, self.system_move)

    def main(self):
        self.draw_board()
        ontimer(self.system_move, 600)
        onscreenclick(self.user_move)
        done()


# Global instance for web API access
_game_instance = None

def get_game() -> TikTakToe:
    """Get or create the game instance (for main.py integration)"""
    global _game_instance
    if _game_instance is None:
        _game_instance = TikTakToe()
    return _game_instance

def launch_game():
    global _game_instance
    _game_instance = TikTakToe()
    _game_instance.main()

if __name__ == '__main__':
    launch_game()