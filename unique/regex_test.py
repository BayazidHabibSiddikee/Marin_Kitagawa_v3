import math

def fib(n):
    a, b = 0, 1
    for _ in range(n):
        print(f"Fibonacci Step: {a}")
        a, b = b, a + b
    return a

print("---  STARTING REGEX TEST FILE  ---")
print(f"Pi Constant: {math.pi}")
print("Executing Sequence...")
fib(15)
print("---  END OF FILE  ---")
