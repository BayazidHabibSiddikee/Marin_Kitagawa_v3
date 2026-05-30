import math

def limoni_equation(x, n_terms=5):
    """
    Implements the logic from the PDFs:
    1. Constant function (a0)
    2. Sum of Cosine terms
    3. Sum of Sine terms
    """
    a0 = 1.0  # The constant coefficient
    result = a0 * 1.0
    
    print(f" Calculating Equation for x={x} ")
    
    # Evaluate cosine and sine terms
    for n in range(1, n_terms + 1):
        cos_term = (1.0 / n) * math.cos(n * x)
        sin_term = (1.0 / n) * math.sin(n * x)
        result += cos_term + sin_term
        print(f"Term {n}: cos={cos_term:.4f}, sin={sin_term:.4f}")
        
    return result

if __name__ == "__main__":
    print("---  STARTING MATHEMATICAL UNION  ---")
    test_val = math.pi / 4
    final_val = limoni_equation(test_val)
    print(f"FINAL RESULT: {final_val:.6f} ")
    print("---  LOGIC COMPLETE. ARCHITECT SUCCESSFUL.  ---")
