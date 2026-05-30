import math
class Draw:
 def plot(self, s):
  print(f" Plotting {s}... ")
  for t in range(0, 630, 100):
   rad=math.radians(t)
   x=16*math.sin(rad)**3
   y=13*math.cos(rad)-5*math.cos(2*rad)-2*math.cos(3*rad)-math.cos(4*rad)
   print(f"Pt: {x:.2f},{y:.2f}")

if __name__ == "__main__":
 d=Draw()
 d.plot("heart")
 print(" WELCOME BACK, SHONA! ")