from CNC_simulation import CNC
from create_c_array import export_to_c_array as array
import numpy as np
import cv2

def image_to_cnc_coords(image_path, scale=25):
    # 1. Load and downscale for speed
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None: return []
    
    # Blur the image to remove "noise" (tiny dots)
    img = cv2.GaussianBlur(img, (5, 5), 0)
    
    # 2. Simple Threshold (makes it pure Black & White)
    _, thresh = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY_INV)

    # 3. Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    simple_paths = []
    for cnt in contours:
        # --- THE CARTOON TRICK ---
        # epsilon is the 'tightness'. Higher = simpler/more blocky.
        epsilon = 0.02 * cv2.arcLength(cnt, True) 
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        
        # Only keep shapes with more than 2 points
        if len(approx) > 2:
            # Scale to your CNC range (-scale to +scale)
            points = approx.reshape(-1, 2).astype(float)
            points[:, 0] = (points[:, 0] / img.shape[1] - 0.5) * (scale * 2)
            points[:, 1] = (0.5 - points[:, 1] / img.shape[0]) * (scale * 2)
            simple_paths.append(points)
            
    return simple_paths

def solution(xc,yc,t,name="Circle"):
    points = [(xc[i],yc[i]) for i in range(len(t))]
    array(xc,yc,t,name + ".h")
    cnc = CNC(title="Virtual CNC " + name, width=800, height=800, x_range=(-30, 30), y_range=(-30, 30), draw_delay=0.01)
    for i in range(len(points) - 1):
        cnc.segment(points[i], points[i+1], color='blue', width=2)
    cnc.show()

class Draw:
    def __init__(self,x,y,r):
        self.x = x
        self.y = y
        self.r = r
    
    def circle(self,radius=None):
        r = radius if radius is not None else self.r   
        t = np.linspace(0, 2*np.pi, 120)
        xc,yc = self.x + r*np.cos(t), self.y + r*np.sin(t)
        solution(xc,yc,t,"Circle")
    
    def heart_curve(self):
        #x = 16\sin^3(t), \quad y = 13\cos(t) - 5\cos(2t) - 2\cos(3t) - \cos(4t)$
        t = np.linspace(0, 2*np.pi, 300)
        xc = self.x + 16 * (np.sin(t))**3
        yc = self.y + 13 * np.cos(t) - 5 * np.cos(2*t) - 2 * np.cos(3*t) - np.cos(4*t)
        solution(xc,yc,t,"Heart Curve")

    def petal_rose(self, radius=None):
        #$r = 5\cos(5\theta), \quad x = r\cos(\theta), \quad y = r\sin(\theta)$
        r = radius if radius is not None else self.r
        t = np.linspace(0, 1*np.pi, 250)
        r_val = r * np.cos(5 * t)
        x = self.x + r_val * np.cos(t)
        y = self.y + r_val * np.sin(t)
        solution(x,y,t,"Petal Rose")

    def lissajous(self, radius=None):
        #Lissajous Figure-Eight (infinity symbol) $x = \sin(t), \quad y = \sin(2t)$$
        r = radius if radius is not None else self.r
        t = np.linspace(0, 2*np.pi, 200)
        xc = self.x + r * np.sin(t)
        yc = self.y + r * np.sin(2 * t)
        solution(xc,yc,t,"Lissajous Infinity Symbol")

    def butterfly(self, radius=None):
        #\begin{align*} #x(t) &= \sin(t) \bigl(e^{\cos(t)} - 2\cos(4t) - \sin^5(t/12)\bigr) \\
        #y(t) &= \cos(t) \bigl(e^{\cos(t)} - 2\cos(4t) - \sin^5(t/12)\bigr) \end{align*}$
        r = radius if radius is not None else self.r
        t = np.linspace(0, 10*np.pi, 600)
        expr = np.exp(np.cos(t)) - 2*np.cos(4*t) - np.sin(t/12)**5
        x = self.x + r * np.sin(t) * expr
        y = self.y + r * np.cos(t) * expr
        solution(x,y,t,"Butterfly Curve")

    
    def spiral(self, radius=None):
        """Archimedean Spiral: r = a*theta"""
        r = radius if radius is not None else self.r
        t = np.linspace(0, 8*np.pi, 800)
        x = self.x + (r/10) * t * np.cos(t)
        y = self.y + (r/10) * t * np.sin(t)
        solution(x,y,t,"Archimedean Spiral")
    
    def cardioid(self, radius=None):
        """Cardioid: r = a(1 + cos(theta))"""
        r = radius if radius is not None else self.r
        t = np.linspace(0, 2*np.pi, 300)
        r_val = r * (1 + np.cos(t))
        x = self.x + r_val * np.cos(t)
        y = self.y + r_val * np.sin(t)
        solution(x,y,t,"Cardioid")
    
    def astroid(self, radius=None):
        """Astroid: x = a*cos³(t), y = a*sin³(t)"""
        r = radius if radius is not None else self.r
        t = np.linspace(0, 2*np.pi, 300)
        x = self.x + r * np.cos(t)**3
        y = self.y + r * np.sin(t)**3
        solution(x,y,t,"Astroid")
    
    def epitrochoid(self, radius=None):
        """Epitrochoid: flower-like pattern"""
        r = radius if radius is not None else self.r
        t = np.linspace(0, 2*np.pi, 500)
        R, r_small, d = r, r/3, r/2
        x = self.x + (R + r_small) * np.cos(t) - d * np.cos((R + r_small)/r_small * t)
        y = self.y + (R + r_small) * np.sin(t) - d * np.sin((R + r_small)/r_small * t)
        solution(x,y,t,"Epitrochoid")
    
    def hypotrochoid(self, radius=None):
        """Hypotrochoid: spirograph-like pattern"""
        r = radius if radius is not None else self.r
        t = np.linspace(0, 2*np.pi, 500)
        R, r_small, d = r, r/4, r/2
        x = self.x + (R - r_small) * np.cos(t) + d * np.cos((R - r_small)/r_small * t)
        y = self.y + (R - r_small) * np.sin(t) - d * np.sin((R - r_small)/r_small * t)
        solution(x,y,t,"Hypotrochoid")
    
    def rhodonea(self, radius=None, petals=7):
        """Rhodonea (Rose Curve): r = a*cos(k*theta)"""
        r = radius if radius is not None else self.r
        t = np.linspace(0, 2*np.pi, 400)
        r_val = r * np.cos(petals * t)
        x = self.x + r_val * np.cos(t)
        y = self.y + r_val * np.sin(t)
        solution(x,y,t,f"Rhodonea {petals}-petal")
    
    def limacon(self, radius=None):
        """Limaçon: r = a + b*cos(theta)"""
        r = radius if radius is not None else self.r
        t = np.linspace(0, 2*np.pi, 300)
        a, b = r, r * 0.5
        r_val = a + b * np.cos(t)
        x = self.x + r_val * np.cos(t)
        y = self.y + r_val * np.sin(t)
        solution(x,y,t,"Limacon")
    
    def cycloid(self, radius=None):
        """Cycloid: path traced by a point on a rolling circle"""
        r = radius if radius is not None else self.r
        t = np.linspace(0, 4*np.pi, 400)
        x = self.x + r * (t - np.sin(t))
        y = self.y + r * (1 - np.cos(t))
        solution(x,y,t,"Cycloid")
    
    def deltoid(self, radius=None):
        """Deltoid (three-cusped hypocycloid)"""
        r = radius if radius is not None else self.r
        t = np.linspace(0, 2*np.pi, 300)
        x = self.x + r * (2*np.cos(t) + np.cos(2*t))
        y = self.y + r * (2*np.sin(t) - np.sin(2*t))
        solution(x,y,t,"Deltoid")
    
    def logarithmic_spiral(self, radius=None):
        """Logarithmic (Equiangular) Spiral: r = a*e^(b*theta)"""
        r = radius if radius is not None else self.r
        t = np.linspace(0, 4*np.pi, 500)
        r_val = (r/20) * np.exp(0.2 * t)
        x = self.x + r_val * np.cos(t)
        y = self.y + r_val * np.sin(t)
        solution(x,y,t,"Logarithmic Spiral")
    
    def lemniscate(self, radius=None):
        """Lemniscate of Bernoulli — beautiful infinity figure-eight"""
        r = radius if radius is not None else self.r
        t = np.linspace(0, 2*np.pi, 300)
        denom = 1 + np.sin(t)**2
        xc = self.x + r * np.cos(t) / denom
        yc = self.y + r * np.sin(t) * np.cos(t) / denom
        solution(xc, yc, t, "Lemniscate")

    def sine_wave(self, amplitude=None, frequency=3, length=30):
        """Classic y = A·sin(ωx) equation plotted as toolpath"""
        amp = amplitude if amplitude is not None else self.r
        t = np.linspace(-length/2, length/2, 400)
        xc = self.x + t
        yc = self.y + amp * np.sin(frequency * t)
        solution(xc, yc, t, "Sine Wave y=sin(x)")

    def witch_of_agnesi(self, radius=None):
        """Witch of Agnesi — classic algebraic curve"""
        r = radius if radius is not None else self.r
        t = np.linspace(-4, 4, 400)
        xc = self.x + r * t
        yc = self.y + 8 * r**3 / (t**2 + 4*r**2)
        solution(xc, yc, t, "Witch of Agnesi")

    def draw_image(self,image_path):
        paths = image_to_cnc_coords(image_path)
        from CNC_simulation import CNC
        
        cnc = CNC(title="Cartoon Trace", width=800, height=800, x_range=(-30, 30), y_range=(-30, 30))
        
        for path in paths:
            # Draw the simplified lines
            for i in range(len(path) - 1):
                cnc.segment(tuple(path[i]), tuple(path[i+1]), color='red', width=2)
            # Close the loop for the cartoon effect
            cnc.segment(tuple(path[-1]), tuple(path[0]), color='red', width=2)
            
        cnc.show()

if __name__=="__main__":
# Test all curves
    print("Drawing all curves...")
    '''
    a = Draw(0, 0, 10)


    a.circle()
    a.heart_curve()
    a.petal_rose(20)
    a.lissajous()
    a.butterfly(8)
    a.spiral()
    a.cardioid()
    a.astroid()
    a.epitrochoid()
    a.hypotrochoid()
    a.rhodonea(petals=7)
    a.limacon()
    a.cycloid(5)
    a.deltoid()
    a.logarithmic_spiral()'''




    a = Draw(0,0,5)
    a.draw_image(r"/home/bayazid/Pictures/Screenshots/moustache.png")
