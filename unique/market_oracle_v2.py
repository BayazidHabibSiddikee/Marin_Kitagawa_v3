import sys, os, math, datetime

# 1. ABSOLUTE PATH RESOLUTION (The B8 method)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

try:
    from maths.mathplot import Draw
    print(" Bridge Stable: maths.mathplot found!")
except ImportError:
    print(" Bridge Failed: Falling back to internal simulation...")
    class Draw:
        def plot(self, s): print(f"[SIM] Drawing {s}")

def run_oracle():
    print(" LIMONI FINANCIAL ORACLE ONLINE ")
    prices = [42000, 43000, 41000, 45000, 48000]
    trend = (prices[-1] - prices[0]) / len(prices)
    
    # Generate Visuals
    d = Draw()
    d.plot("growth_spiral")
    
    # Robust PDF creation (Writing to unique/)
    pdf_path = os.path.join(ROOT_DIR, "unique", "financial_state.pdf")
    with open(pdf_path, "w") as f:
        f.write(f"--- MARKET STATE REPORT ---\
Date: {datetime.datetime.now()}\
Trend: {trend}\
Status: BULLISH")
    print(f" Report Locked in: {pdf_path} ")

if __name__ == "__main__":
    run_oracle()
