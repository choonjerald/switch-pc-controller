"""Local Windows controls for pairing and editing the nine-button layouts."""

from copy import deepcopy
from pathlib import Path
from tkinter import Menu, StringVar, Text, Tk, colorchooser, filedialog, messagebox, simpledialog, ttk

from macro_pad import read_profiles, save_profiles


class ProfileEditor:
    def __init__(self, root, pad, path):
        self.root, self.pad, self.path = root, pad, path
        self.profile_index = self.slot = 0
        self.profile_name = StringVar()
        self.label = StringVar()
        self.icon = StringVar()
        self.color = StringVar()
        self.position = StringVar()
        self.choosing_position = False
        self.status = StringVar()
        self.note = StringVar()
        root.title("Switch macro pad")
        menu = Menu(root)
        files = Menu(menu, tearoff=False)
        files.add_command(label="Import profiles…", command=self.import_profiles)
        files.add_command(label="Export profiles…", command=self.export_profiles)
        menu.add_cascade(label="File", menu=files)
        root.configure(menu=menu)
        main = ttk.Frame(root, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(2, weight=1)

        controls = ttk.Frame(main)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        controls.columnconfigure(0, weight=1)
        ttk.Label(controls, textvariable=self.status, font=("Segoe UI", 14)).grid(row=0, column=0, sticky="w")
        ttk.Button(controls, text="Enable pairing", command=lambda: pad.arm("Macros, trackpad and typing")).grid(row=0, column=1, padx=4)
        ttk.Button(controls, text="Disable input", command=pad.disable).grid(row=0, column=2)

        profiles = ttk.Frame(main)
        profiles.grid(row=1, column=0, columnspan=2, sticky="ew", pady=6)
        self.profiles = ttk.Frame(profiles)
        self.profiles.pack(side="left", fill="x", expand=True)
        for title, callback in [("New", self.new_profile), ("Rename", self.rename_profile), ("Delete", self.delete_profile)]:
            ttk.Button(profiles, text=title, width=8, command=callback).pack(side="left", padx=2)

        grid = ttk.Frame(main)
        grid.grid(row=2, column=0, sticky="nsew", padx=(0, 12))
        self.tiles = []
        for i in range(9):
            row, col = divmod(i, 3)
            grid.rowconfigure(row, weight=1)
            grid.columnconfigure(col, weight=1, uniform="slots")
            tile = ttk.Button(grid, width=12, command=lambda slot=i: self.click_slot(slot))
            tile.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
            self.tiles.append(tile)

        edit = ttk.LabelFrame(main, text="Button mapping", padding=10)
        edit.grid(row=2, column=1, sticky="nsew")
        edit.columnconfigure(1, weight=1)
        for row, (title, value) in enumerate([("Label", self.label), ("Icon", self.icon), ("Color", self.color)]):
            ttk.Label(edit, text=title).grid(row=row, column=0, sticky="w", padx=(0, 5))
            ttk.Entry(edit, textvariable=value, width=24).grid(row=row, column=1, sticky="ew", pady=2)
        ttk.Button(edit, text="Pick", width=5, command=self.pick_color).grid(row=2, column=2)
        ttk.Label(edit, text="Position").grid(row=3, column=0, sticky="w")
        ttk.Label(edit, textvariable=self.position).grid(row=3, column=1, sticky="w")
        ttk.Button(edit, text="Move…", command=self.choose_position).grid(row=3, column=2)
        ttk.Label(edit, text="Actions in order").grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 2))
        self.actions = Text(edit, height=7, width=29, wrap="none", font=("Consolas", 10))
        self.actions.grid(row=5, column=0, columnspan=3, sticky="nsew")
        edit.rowconfigure(5, weight=1)
        ttk.Label(edit, text="One per line, e.g. tap Ctrl+C or wait 150").grid(row=6, column=0, columnspan=3, sticky="w")
        buttons = ttk.Frame(edit)
        buttons.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Save button", command=self.save_button).pack(side="left")
        ttk.Button(buttons, text="Clear slot", command=self.clear_slot).pack(side="right")
        ttk.Label(main, textvariable=self.note, wraplength=640).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.select_profile(0)
        self.refresh_status()

    def refresh_status(self):
        self.status.set(self.pad.status())
        self.root.after(250, self.refresh_status)

    def select_profile(self, index, slot=0):
        self.profile_index = index
        self.profile_name.set(self.pad.profiles[index]["name"])
        for widget in self.profiles.winfo_children():
            widget.destroy()
        for i, profile in enumerate(self.pad.profiles):
            choice = ttk.Radiobutton(self.profiles, text=profile["name"], value=profile["name"],
                                     variable=self.profile_name, command=lambda n=i: self.select_profile(n))
            choice.grid(row=i // 3, column=i % 3, sticky="w", padx=3)
        for i, button in enumerate(self.pad.profiles[index]["buttons"]):
            text = (button["icon"] + "\n" + button["label"]) if button else f"Empty {i + 1}"
            self.tiles[i].configure(text=text)
        self.select_slot(slot)

    def select_slot(self, slot):
        self.slot = slot
        self.choosing_position = False
        for i, tile in enumerate(self.tiles):
            tile.state(["pressed" if i == slot else "!pressed"])
        button = self.pad.profiles[self.profile_index]["buttons"][slot]
        self.label.set(button["label"] if button else "")
        self.icon.set(button["icon"] if button else "")
        self.color.set(button["color"] if button else "#7ddbc0")
        self.position.set(str(slot + 1))
        self.actions.delete("1.0", "end")
        self.actions.insert("1.0", "\n".join(button["steps"]) if button else "")
        self.note.set(f"Editing slot {slot + 1}")

    def choose_position(self):
        self.choosing_position = True
        self.note.set("Click the destination slot in the grid.")

    def click_slot(self, slot):
        if self.choosing_position:
            self.choosing_position = False
            self.position.set(str(slot + 1))
            self.note.set(f"Click Save button to move this mapping to slot {slot + 1}.")
        else:
            self.select_slot(slot)

    def commit(self, profiles, index, slot=0):
        try:
            save_profiles(self.path, profiles)
        except (ValueError, OSError) as exc:
            self.note.set(str(exc))
            return
        self.pad.set_profiles(profiles)
        self.select_profile(index, slot)
        self.note.set(f"Saved to {self.path}")

    def pick_color(self):
        color = colorchooser.askcolor(parent=self.root, title="Button accent")[1]
        if color:
            self.color.set(color)

    def import_profiles(self):
        filename = filedialog.askopenfilename(parent=self.root, title="Import profiles", filetypes=[("JSON", "*.json")])
        if not filename:
            return
        try:
            profiles = read_profiles(Path(filename))
        except (ValueError, OSError) as exc:
            self.note.set(str(exc))
            return
        if messagebox.askyesno("Import profiles", f"Replace the current profiles with {len(profiles)} imported profiles?",
                               parent=self.root):
            self.commit(profiles, 0)

    def export_profiles(self):
        filename = filedialog.asksaveasfilename(parent=self.root, title="Export profiles", initialfile="profiles.json",
                                                defaultextension=".json", filetypes=[("JSON", "*.json")])
        if filename:
            try:
                save_profiles(Path(filename), self.pad.profiles)
                self.note.set(f"Exported to {filename}")
            except (ValueError, OSError) as exc:
                self.note.set(str(exc))

    def save_button(self):
        profiles = deepcopy(self.pad.profiles)
        buttons = profiles[self.profile_index]["buttons"]
        target = int(self.position.get()) - 1
        # Moving a mapped button swaps it with the destination.
        buttons[self.slot] = buttons[target]
        buttons[target] = {"label": self.label.get().strip(), "icon": self.icon.get().strip(),
                           "color": self.color.get().strip(),
                           "steps": [s.strip() for s in self.actions.get("1.0", "end").splitlines() if s.strip()]}
        self.commit(profiles, self.profile_index, target)

    def clear_slot(self):
        if messagebox.askyesno("Clear slot", f"Remove the mapping from slot {self.slot + 1}?", parent=self.root):
            profiles = deepcopy(self.pad.profiles)
            profiles[self.profile_index]["buttons"][self.slot] = None
            self.commit(profiles, self.profile_index, self.slot)

    def new_profile(self):
        name = simpledialog.askstring("New profile", "Profile name", parent=self.root)
        if name:
            profiles = deepcopy(self.pad.profiles)
            profiles.append({"name": name.strip(), "buttons": [None] * 9})
            self.commit(profiles, len(profiles) - 1)

    def rename_profile(self):
        name = simpledialog.askstring("Rename profile", "Profile name", initialvalue=self.profile_name.get(), parent=self.root)
        if name:
            profiles = deepcopy(self.pad.profiles)
            profiles[self.profile_index]["name"] = name.strip()
            self.commit(profiles, self.profile_index, self.slot)

    def delete_profile(self):
        if len(self.pad.profiles) == 1:
            self.note.set("Keep at least one profile.")
            return
        if messagebox.askyesno("Delete profile", f"Delete {self.profile_name.get()} and its mappings?", parent=self.root):
            profiles = deepcopy(self.pad.profiles)
            del profiles[self.profile_index]
            self.commit(profiles, min(self.profile_index, len(profiles) - 1))


def show_editor(pad, path):
    root = Tk()
    ProfileEditor(root, pad, path)
    root.mainloop()
