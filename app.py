"""Desktop control panel. Camera operations run in a separate process."""
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from security.core import Database

ROOT = Path(__file__).resolve().parent


class SecurityApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Smart Society | Security Control Center')
        self.geometry('1100x760')
        self.minsize(860, 640)
        self.configure(bg='#101827')
        self.process = None
        self.messages = queue.Queue()
        self.db_path = ROOT / 'data' / 'society.db'
        self.status = tk.StringVar(value='Ready — enroll residents to begin')
        self.progress = tk.StringVar()
        self.resident_id = tk.StringVar()
        self.resident_name = tk.StringVar()
        self.apartment = tk.StringVar()
        self.camera = tk.StringVar(value='0')
        self.threshold = tk.StringVar(value='0.48')
        self.samples = tk.StringVar(value='5')
        self.consent = tk.BooleanVar(value=False)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#101827')
        style.configure('TLabel', background='#101827', foreground='#e2e8f0', font=('Helvetica', 11))
        style.configure('Title.TLabel', font=('Helvetica', 24, 'bold'))
        style.configure('Accent.TButton', background='#2563eb', foreground='white', padding=10)
        style.configure('TButton', padding=7)
        style.configure('Treeview', rowheight=29)
        header = ttk.Frame(self, padding=24)
        header.pack(fill='x')
        ttk.Label(header, text='Smart Society', style='Title.TLabel').pack(anchor='w')
        ttk.Label(header, text='SECURITY CONTROL CENTER  •  Local face recognition prototype').pack(anchor='w', pady=(8, 0))
        ttk.Label(header, textvariable=self.progress).pack(anchor='w', pady=(10, 0))
        tabs = ttk.Notebook(self)
        tabs.pack(fill='both', expand=True, padx=24)
        enroll = ttk.Frame(tabs, padding=22)
        live = ttk.Frame(tabs, padding=22)
        residents = ttk.Frame(tabs, padding=16)
        logs = ttk.Frame(tabs, padding=16)
        evaluation = ttk.Frame(tabs, padding=22)
        for title, frame in [('Enrollment', enroll), ('Live monitor', live), ('Residents', residents),
                             ('Entry logs', logs), ('Evaluation', evaluation)]:
            tabs.add(frame, text=title)
        self.field(enroll, 'Resident ID', self.resident_id)
        self.field(enroll, 'Full name', self.resident_name)
        self.field(enroll, 'Apartment', self.apartment)
        self.field(enroll, 'Webcam samples (1–30)', self.samples)
        ttk.Checkbutton(enroll, text='This person has consented to local face enrollment', variable=self.consent).pack(anchor='w', pady=12)
        ttk.Button(enroll, text='Enroll with webcam', style='Accent.TButton', command=lambda: self.enroll(False)).pack(anchor='w', pady=6)
        ttk.Button(enroll, text='Enroll from photos', command=lambda: self.enroll(True)).pack(anchor='w', pady=6)
        ttk.Label(enroll, text='Use several clear photos of the same person. One face per image.').pack(anchor='w', pady=12)
        self.field(live, 'Camera index (usually 0)', self.camera)
        self.field(live, 'Matching threshold (0–1)', self.threshold)
        ttk.Label(live, text='Green: Entry Allowed    •    Red: Entry Rejected\nNo face: waiting for a person', justify='left').pack(anchor='w', pady=18)
        ttk.Button(live, text='Start live monitor', style='Accent.TButton', command=self.monitor).pack(anchor='w', pady=8)
        ttk.Button(live, text='Stop camera operation', command=self.stop).pack(anchor='w', pady=8)
        ttk.Label(live, text='The camera opens in a separate window. Press Q in that window to stop.\nAcademic demonstration only; no liveness detection or physical gate control.').pack(anchor='w', pady=16)
        self.resident_tree = self.table(residents, ('id', 'name', 'apartment', 'active', 'samples'))
        buttons = ttk.Frame(residents)
        buttons.pack(fill='x', pady=10)
        ttk.Button(buttons, text='Refresh', command=self.refresh).pack(side='left', padx=4)
        ttk.Button(buttons, text='Activate selected', command=lambda: self.set_active(True)).pack(side='left', padx=4)
        ttk.Button(buttons, text='Deactivate selected', command=lambda: self.set_active(False)).pack(side='left', padx=4)
        self.log_tree = self.table(logs, ('timestamp', 'resident_id', 'decision', 'distance', 'reason'))
        ttk.Button(logs, text='Refresh logs', command=self.refresh).pack(side='left', pady=10)
        ttk.Button(logs, text='Export logs CSV', command=self.export).pack(side='left', padx=12, pady=10)
        ttk.Label(evaluation, text='Measure performance using held-out images', style='Title.TLabel').pack(anchor='w', pady=12)
        ttk.Label(evaluation, text='Select a CSV containing image and expected_id columns.\nLeave expected_id blank for unregistered visitors.\nUse photos that were not used for enrollment.').pack(anchor='w', pady=12)
        ttk.Button(evaluation, text='Select CSV and generate report', style='Accent.TButton', command=self.evaluate).pack(anchor='w', pady=12)
        ttk.Label(evaluation, text='Reports: reports/evaluation.md and reports/evaluation.json\nIncludes accuracy, false positives, false negatives and identity errors.').pack(anchor='w', pady=12)
        ttk.Label(self, textvariable=self.status, wraplength=1000).pack(fill='x', padx=24, pady=10)
        self.console = tk.Text(self, height=7, bg='#0b1220', fg='#cbd5e1', font=('Courier', 10), state='disabled')
        self.console.pack(fill='x', padx=24, pady=(0, 18))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()
        self.after(150, self.poll)

    @staticmethod
    def field(parent, label, variable):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=5)
        ttk.Label(row, text=label, width=26).pack(side='left')
        ttk.Entry(row, textvariable=variable, width=32).pack(side='left')

    @staticmethod
    def table(parent, columns):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
        for col in columns:
            tree.heading(col, text=col.replace('_', ' ').title())
            tree.column(col, width=160 if col == 'timestamp' else 120, minwidth=65)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        return tree

    def append(self, text):
        self.console.configure(state='normal')
        self.console.insert('end', text + '\n')
        self.console.see('end')
        self.console.configure(state='disabled')

    def run_command(self, args):
        if self.process is not None:
            messagebox.showinfo('Operation running', 'Stop or finish the current operation first.')
            return
        try:
            self.process = subprocess.Popen([sys.executable, '-u', str(ROOT/'main.py'), '--db', str(self.db_path), *args],
                                            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, encoding='utf-8', errors='replace')
        except OSError as exc:
            messagebox.showerror('Cannot start', str(exc))
            return
        self.status.set('Running: ' + args[0])
        self.append('> ' + ' '.join(args))
        process = self.process

        def read_output():
            for line in process.stdout:
                self.messages.put(('line', line.rstrip()))
            process.stdout.close()
            self.messages.put(('done', process.wait()))
        threading.Thread(target=read_output, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == 'line':
                    self.append(value)
                else:
                    self.process = None
                    self.status.set('Operation completed' if value == 0 else f'Operation stopped or failed (exit {value}); see details below')
                    self.refresh()
        except queue.Empty:
            pass
        self.after(150, self.poll)

    def settings(self):
        index = int(self.camera.get())
        threshold = float(self.threshold.get())
        if index < 0 or not 0 < threshold < 1:
            raise ValueError('Use a camera index of 0 or higher and a threshold between 0 and 1.')
        return index, threshold

    def enroll(self, photos):
        try:
            values = [v.get().strip() for v in (self.resident_id, self.resident_name, self.apartment)]
            if not all(values) or not self.consent.get():
                raise ValueError('Enter all resident details and confirm enrollment consent.')
            count = int(self.samples.get())
            if not 1 <= count <= 30:
                raise ValueError('Sample count must be 1 through 30.')
            args = ['register', '--id', values[0], '--name', values[1], '--apartment', values[2]]
            if photos:
                files = filedialog.askopenfilenames(title='Select this resident’s photos', filetypes=[('Images', '*.jpg *.jpeg *.png')])
                if not files:
                    return
                args += ['--images', *files]
            else:
                index, _ = self.settings()
                args += ['--camera', str(index), '--samples', str(count)]
            self.run_command(args)
        except ValueError as exc:
            messagebox.showerror('Check enrollment', str(exc))

    def monitor(self):
        try:
            index, threshold = self.settings()
            self.run_command(['monitor', '--camera', str(index), '--threshold', str(threshold)])
        except ValueError as exc:
            messagebox.showerror('Check settings', str(exc))

    def refresh(self):
        db = Database(self.db_path)
        try:
            residents, events = db.residents(), db.events()
        finally:
            db.close()
        count = sum(bool(r['active'] and r['samples']) for r in residents)
        self.progress.set(f'{count} / 20 residents enrolled and active  |  {len(events)} entry events')
        for tree, rows, columns in [(self.resident_tree, residents, ('id','name','apartment','active','samples')),
                                     (self.log_tree, events[:500], ('timestamp','resident_id','decision','distance','reason'))]:
            tree.delete(*tree.get_children())
            for row in rows:
                tree.insert('', 'end', values=[row[c] if row[c] is not None else '—' for c in columns])

    def set_active(self, active):
        if self.process is not None:
            messagebox.showinfo('Operation running', 'Finish or stop the current operation before changing resident access.')
            return
        selected = self.resident_tree.selection()
        if not selected:
            messagebox.showinfo('Select resident', 'Select a resident in the table first.')
            return
        resident_id = str(self.resident_tree.item(selected[0], 'values')[0])
        db = Database(self.db_path)
        try:
            db.set_active(resident_id, active)
        finally:
            db.close()
        self.refresh()

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='entry_logs.csv')
        if path:
            self.run_command(['logs', '--csv', path])

    def evaluate(self):
        try:
            _, threshold = self.settings()
            path = filedialog.askopenfilename(filetypes=[('CSV manifest', '*.csv')])
            if path:
                self.run_command(['evaluate', path, '--threshold', str(threshold)])
        except ValueError as exc:
            messagebox.showerror('Check threshold', str(exc))

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            self.status.set('Stopping camera operation…')

    def close(self):
        self.stop()
        self.destroy()


if __name__ == '__main__':
    SecurityApp().mainloop()
