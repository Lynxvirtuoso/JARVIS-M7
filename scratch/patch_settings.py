import urllib.parse

with open('ui/settings/window.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

idx_tabs = -1
for i, line in enumerate(lines):
    if 'VOICE PROVIDERS' in line and 'addTab' in line:
        idx_tabs = i
        break

if idx_tabs == -1:
    print('Error: VOICE PROVIDERS not found')
    exit(1)

idx_save = -1
for i, line in enumerate(lines):
    if 'def save_settings(self):' in line:
        idx_save = i
        break

if idx_save == -1:
    print('Error: save_settings not found')
    exit(1)

tab_inserts = [
    '        # --- TAB 4: AI / API CONFIG ---\n',
    '        tab_ai_api = QWidget()\n',
    '        form_ai_api = QFormLayout(tab_ai_api)\n',
    '        form_ai_api.setContentsMargins(15, 15, 15, 15)\n',
    '        form_ai_api.setSpacing(12)\n',
    '        self.stt_mode_combo = QComboBox(self)\n',
    '        self.stt_mode_combo.addItems(["offline_only", "offline_first_cloud_fallback", "cloud_first"])\n',
    '        self.stt_mode_combo.setCurrentText(config.get("stt_mode", "offline_first_cloud_fallback"))\n',
    '        form_ai_api.addRow("STT MODE:", self.stt_mode_combo)\n',
    '        self.cloud_intent_cb = QCheckBox("Enable Optional Cloud Intent normalizer", self)\n',
    '        self.cloud_intent_cb.setChecked(config.get("enable_cloud_intent", "false").lower() == "true")\n',
    '        form_ai_api.addRow("CLOUD INTENT:", self.cloud_intent_cb)\n',
    '        self.intent_prov_combo = QComboBox(self)\n',
    '        self.intent_prov_combo.addItems(["none", "gemini", "openai"])\n',
    '        self.intent_prov_combo.setCurrentText(config.get("intent_provider", "none"))\n',
    '        form_ai_api.addRow("INTENT PROVIDER:", self.intent_prov_combo)\n',
    '        self.ai_api_gemini_edit = QLineEdit(self)\n',
    '        self.ai_api_gemini_edit.setEchoMode(QLineEdit.EchoMode.Password)\n',
    '        self.ai_api_gemini_edit.setText(config.get("gemini_api_key", ""))\n',
    '        form_ai_api.addRow("GEMINI API KEY:", self.ai_api_gemini_edit)\n',
    '        self.ai_api_openai_edit = QLineEdit(self)\n',
    '        self.ai_api_openai_edit.setEchoMode(QLineEdit.EchoMode.Password)\n',
    '        self.ai_api_openai_edit.setText(config.get("openai_api_key", ""))\n',
    '        form_ai_api.addRow("OPENAI API KEY:", self.ai_api_openai_edit)\n',
    '        self.tabs.addTab(tab_ai_api, "AI / API")\n',
    '        # --- TAB 5: APPS & ACTIONS ---\n',
    '        tab_apps = QWidget()\n',
    '        vbox_apps = QVBoxLayout(tab_apps)\n',
    '        vbox_apps.setContentsMargins(15, 15, 15, 15)\n',
    '        vbox_apps.setSpacing(10)\n',
    '        self.refresh_index_btn = QPushButton("REFRESH WINDOWS APP INDEX", self)\n',
    '        self.refresh_index_btn.clicked.connect(self.refresh_app_index_clicked)\n',
    '        vbox_apps.addWidget(self.refresh_index_btn)\n',
    '        vbox_apps.addWidget(QLabel("MANUAL APP VOICE ALIASES:", self))\n',
    '        self.aliases_list_widget = QListWidget(self)\n',
    '        self.load_app_aliases_to_ui()\n',
    '        vbox_apps.addWidget(self.aliases_list_widget)\n',
    '        h_add = QHBoxLayout()\n',
    '        self.alias_input = QLineEdit(self)\n',
    '        self.alias_input.setPlaceholderText("Voice Alias (e.g. edge)")\n',
    '        self.app_name_input = QLineEdit(self)\n',
    '        self.app_name_input.setPlaceholderText("Canonical App Display Name (e.g. Microsoft Edge)")\n',
    '        h_add.addWidget(self.alias_input)\n',
    '        h_add.addWidget(self.app_name_input)\n',
    '        self.add_alias_pair_btn = QPushButton("ADD ALIAS", self)\n',
    '        self.add_alias_pair_btn.clicked.connect(self.add_alias_pair)\n',
    '        h_add.addWidget(self.add_alias_pair_btn)\n',
    '        vbox_apps.addLayout(h_add)\n',
    '        self.remove_alias_pair_btn = QPushButton("REMOVE SELECTED ALIAS", self)\n',
    '        self.remove_alias_pair_btn.clicked.connect(self.remove_selected_alias_pair)\n',
    '        vbox_apps.addWidget(self.remove_alias_pair_btn)\n',
    '        self.tabs.addTab(tab_apps, "APPS & ACTIONS")\n'
]

new_lines = lines[:idx_tabs+1] + tab_inserts + lines[idx_tabs+1:]

idx_save_new = idx_save + len(tab_inserts)

helper_inserts = [
    '    def load_app_aliases_to_ui(self):\n',
    '        self.aliases_list_widget.clear()\n',
    '        try:\n',
    '            import os\n',
    '            import json\n',
    '            alias_path = os.path.join("config", "app_aliases.json")\n',
    '            if os.path.exists(alias_path):\n',
    '                with open(alias_path, "r", encoding="utf-8") as f:\n',
    '                    data = json.load(f)\n',
    '                for k, v in data.items():\n',
    '                    self.aliases_list_widget.addItem(f"{k} -> {v}")\n',
    '        except Exception as e:\n',
    '            logger.error(f"Failed to load app_aliases: {e}")\n',
    '\n',
    '    def add_alias_pair(self):\n',
    '        alias_text = self.alias_input.text().strip().lower()\n',
    '        app_text = self.app_name_input.text().strip()\n',
    '        if alias_text and app_text:\n',
    '            try:\n',
    '                import os\n',
    '                import json\n',
    '                alias_path = os.path.join("config", "app_aliases.json")\n',
    '                data = {}\n',
    '                if os.path.exists(alias_path):\n',
    '                    with open(alias_path, "r", encoding="utf-8") as f:\n',
    '                        data = json.load(f)\n',
    '                data[alias_text] = app_text\n',
    '                os.makedirs("config", exist_ok=True)\n',
    '                with open(alias_path, "w", encoding="utf-8") as f:\n',
    '                    json.dump(data, f, indent=4)\n',
    '                self.load_app_aliases_to_ui()\n',
    '                self.alias_input.clear()\n',
    '                self.app_name_input.clear()\n',
    '                bus.console_log.emit("INFO", f"Added app alias: \'{alias_text}\' -> \'{app_text}\'")\n',
    '            except Exception as e:\n',
    '                logger.error(f"Failed to add app alias: {e}")\n',
    '\n',
    '    def remove_selected_alias_pair(self):\n',
    '        item = self.aliases_list_widget.currentItem()\n',
    '        if item:\n',
    '            text = item.text()\n',
    '            if " -> " in text:\n',
    '                alias_key = text.split(" -> ")[0].strip()\n',
    '                try:\n',
    '                    import os\n',
    '                    import json\n',
    '                    alias_path = os.path.join("config", "app_aliases.json")\n',
    '                    if os.path.exists(alias_path):\n',
    '                        with open(alias_path, "r", encoding="utf-8") as f:\n',
    '                            data = json.load(f)\n',
    '                        if alias_key in data:\n',
    '                            del data[alias_key]\n',
    '                            with open(alias_path, "w", encoding="utf-8") as f:\n',
    '                                json.dump(data, f, indent=4)\n',
    '                            self.load_app_aliases_to_ui()\n',
    '                            bus.console_log.emit("INFO", f"Removed app alias for \'{alias_key}\'")\n',
    '                except Exception as e:\n',
    '                    logger.error(f"Failed to remove alias: {e}")\n',
    '\n',
    '    def refresh_app_index_clicked(self):\n',
    '        self.refresh_index_btn.setEnabled(False)\n',
    '        self.refresh_index_btn.setText("DISCOVERING APPS...")\n',
    '        def run_disc():\n',
    '            try:\n',
    '                from services.app_discovery_service import app_discovery_service\n',
    '                apps = app_discovery_service.discover_all()\n',
    '                bus.console_log.emit("INFO", f"Discovered {len(apps)} apps successfully.")\n',
    '            except Exception as e:\n',
    '                logger.error(f"Discovery error: {e}")\n',
    '            finally:\n',
    '                self.refresh_index_btn.setEnabled(True)\n',
    '                self.refresh_index_btn.setText("REFRESH WINDOWS APP INDEX")\n',
    '        import threading\n',
    '        threading.Thread(target=run_disc, daemon=True).start()\n',
    '\n'
]

new_lines = new_lines[:idx_save_new] + helper_inserts + new_lines[idx_save_new:]

idx_save_body = idx_save_new + len(helper_inserts) + 1

save_body_inserts = [
    '        config.set("stt_mode", self.stt_mode_combo.currentText())\n',
    '        config.set("enable_cloud_intent", "true" if self.cloud_intent_cb.isChecked() else "false")\n',
    '        config.set("intent_provider", self.intent_prov_combo.currentText())\n',
    '        if self.ai_api_gemini_edit.text().strip():\n',
    '            config.set("gemini_api_key", self.ai_api_gemini_edit.text().strip())\n',
    '        if self.ai_api_openai_edit.text().strip():\n',
    '            config.set("openai_api_key", self.ai_api_openai_edit.text().strip())\n'
]

new_lines = new_lines[:idx_save_body] + save_body_inserts + new_lines[idx_save_body:]

with open('ui/settings/window.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('SUCCESS!')
