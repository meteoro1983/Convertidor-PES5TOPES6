"""Prueba de la logica de la ventana SIN pantalla: se sustituye tkinter por una version falsa."""
import sys, types, time, os, importlib.util
pend=[]; llamadas=[]
class Var:
    def __init__(s,value=None): s.v=value
    def get(s): return s.v
    def set(s,v): s.v=v
class Widget:
    def __init__(s,*a,**k): s.cfg=k; s.texto=""
    def grid(s,*a,**k): return s
    def configure(s,**k):
        s.cfg.update(k)
        if 'text' in k: s.texto=k['text']
    config=configure
    def insert(s,i,t): s.texto+=t
    def delete(s,*a): s.texto=""
    def see(s,*a): pass
class Tk(Widget):
    def title(s,t): pass
    def geometry(s,g): pass
    def after(s,ms,fn): pend.append((time.time()+ms/1000.0,fn))
    def mainloop(s):
        t0=time.time()
        while time.time()-t0<300:
            if any(c[0] in('info','error') for c in llamadas): break
            pend.sort(key=lambda x:x[0])
            if pend:
                t,fn=pend.pop(0)
                time.sleep(max(0,t-time.time())); fn()
            else: time.sleep(0.05)
tk=types.ModuleType('tkinter'); tk.Tk=Tk; tk.StringVar=Var; tk.BooleanVar=Var; tk.Text=Widget
ttk=types.ModuleType('tkinter.ttk')
for n in('Label','Entry','Button','Checkbutton'): setattr(ttk,n,Widget)
fd=types.ModuleType('tkinter.filedialog'); fd.askopenfilename=lambda **k:''; fd.askdirectory=lambda **k:''
mb=types.ModuleType('tkinter.messagebox')
mb.showinfo=lambda t,m: llamadas.append(('info',t,m)); mb.showerror=lambda t,m: llamadas.append(('error',t,m)); mb.showwarning=lambda t,m: llamadas.append(('warn',t,m))
tk.ttk=ttk; tk.filedialog=fd; tk.messagebox=mb
for n,m in (('tkinter',tk),('tkinter.ttk',ttk),('tkinter.filedialog',fd),('tkinter.messagebox',mb)): sys.modules[n]=m
spec=importlib.util.spec_from_file_location('conv',os.path.join(os.path.dirname(__file__),'..','we9_a_pes6.py')); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
entrada=sys.argv[1]
print('--- caso 1: archivo arrastrado sobre el .exe (conversion automatica)')
m.main_gui(entrada)
print('mensajes:',[(c[0],c[2][:90].replace(chr(10),' | ')) for c in llamadas])
print('--- caso 2: archivo inexistente (debe mostrar error claro)')
llamadas.clear(); pend.clear()
m.main_gui('/no/existe/archivo')
print('mensajes:',[(c[0],c[2][:90]) for c in llamadas])
