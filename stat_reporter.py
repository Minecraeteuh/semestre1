# stat_reporter.py

import time, socket, platform, subprocess, glob, re
import sys
import argparse
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

def _safe_read(path, default_value="N/D", conversion=str):
    try:
        with open(path, 'r') as f:
            return conversion(f.read().strip())
    except Exception:
        return default_value

def _safe_subprocess(cmd, default_value="N/D", timeout=5):
    try:
        result = subprocess.check_output(
            cmd,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout
        ).strip()
        return result
    except Exception:
        return default_value

class SystemCollector:
    def get_general_info(self):
        report_time = time.strftime("%Y-%m-%d %H:%M:%S")
        uptime_sec = _safe_read("/proc/uptime", default_value=0.0, conversion=lambda x: float(x.split()[0]))
        if uptime_sec != 0.0:
            h = int(uptime_sec // 3600)
            m = int((uptime_sec % 3600) // 60)
            s = int(uptime_sec % 60)
            uptime_str = f"{h}h {m}min {s}sec"
        else:
            uptime_str = "Erreur de lecture de l'uptime"

        return {
            "time": report_time,
            "hostname": socket.gethostname(),
            "kernel": f"{platform.system()} {platform.release()}",
            "uptime": uptime_str,
        }

    def get_memory_stats(self):
        meminfo = _safe_read("/proc/meminfo", default_value="")
        mem_values = {}
        for line in meminfo.splitlines():
            match = re.match(r'(\w+):\s+(\d+)', line)
            if match:
                mem_values[match.group(1)] = int(match.group(2))

        total_ram_ko = mem_values.get('MemTotal', 0)
        available_ram_ko = mem_values.get('MemAvailable', 0)
        cached_buffers_ko = mem_values.get('Cached', 0) + mem_values.get('Buffers', 0)
        total_swap_ko = mem_values.get('SwapTotal', 0)
        free_swap_ko = mem_values.get('SwapFree', 0)

        used_ram_ko = total_ram_ko - available_ram_ko
        used_percent = round((used_ram_ko / total_ram_ko) * 100, 1) if total_ram_ko > 0 else 0
        
        used_swap_ko = total_swap_ko - free_swap_ko
        swap_percent = round((used_swap_ko / total_swap_ko) * 100, 1) if total_swap_ko > 0 else 0

        ko_to_gb = 1048576 
            
        return {
            "total_gb": round(total_ram_ko / ko_to_gb, 2),
            "used_gb": round(used_ram_ko / ko_to_gb, 2),
            "cache_gb": round(cached_buffers_ko / ko_to_gb, 2),
            "used_percent": used_percent,
            "swap_total_gb": round(total_swap_ko / ko_to_gb, 2),
            "swap_used_percent": swap_percent,
        }

    def get_temperatures(self):
        temps = {}
        for path in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
            try:
                name_path = path.replace('temp', 'type')
                sensor_name = _safe_read(name_path, default_value=path.split('/')[-2])
                temp_raw = _safe_read(path, conversion=int)
                
                if isinstance(temp_raw, int):
                    temps[sensor_name.capitalize()] = f"{temp_raw / 1000:.1f}°C"
            except Exception:
                continue 

        gpu_temp_raw = _safe_subprocess(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"]
        )
        if gpu_temp_raw.isdigit():
            temps["GPU (NVIDIA)"] = f"{gpu_temp_raw}°C"
        elif "N/D" not in gpu_temp_raw and gpu_temp_raw != "":
             temps["GPU (NVIDIA)"] = "Erreur lecture GPU"
        
        return temps if temps else {"Erreur": "Aucun capteur thermique trouvé."}

    def get_power_supply(self):
        power_paths = glob.glob("/sys/class/power_supply/B*") + glob.glob("/sys/class/power_supply/A*")
        power_data = []

        if not power_paths:
            return {"source": "N/D", "status": "Non-portable", "capacity": "N/D"}

        for path in power_paths:
            name = path.split('/')[-1]
            status = _safe_read(f"{path}/status", default_value="Inconnu")
            capacity = _safe_read(f"{path}/capacity", default_value="N/D")
            
            capacity_str = f"{capacity}%" if capacity.isdigit() else capacity
            
            power_data.append({
                "source": name,
                "status": status,
                "capacity": capacity_str
            })
            if name.startswith("BAT") or name.startswith("AC"):
                break

        return power_data[0] if power_data else {"source": "N/D", "status": "N/D", "capacity": "N/D"}

    def get_process_list(self):
        processes = []
        pids = [p.split('/')[-1] for p in glob.glob("/proc/[0-9]*")]
        
        for pid in pids:
            try:
                status_path = f"/proc/{pid}/status"
                content = _safe_read(status_path, default_value="")
                
                name_match = re.search(r'Name:\s*([^\n]+)', content)
                uid_match = re.search(r'Uid:\s*(\d+)', content)
                mem_match = re.search(r'VmRSS:\s*(\d+)', content)
                
                nom = name_match.group(1).strip() if name_match else f"PID {pid}"
                uid = uid_match.group(1) if uid_match else "N/A"
                mem_ko = int(mem_match.group(1)) if mem_match else 0
                
                user_name = _safe_subprocess(["id", "-un", uid], default_value=f"UID {uid}")

                processes.append({
                    "pid": pid,
                    "user": user_name,
                    "mem_ko": mem_ko,
                    "name": nom,
                    "cpu_percent": "N/D"
                })
            except Exception:
                continue 
                
        return sorted(processes, key=lambda p: p['mem_ko'], reverse=True)[:30]

    def get_disk_usage(self):
        output = _safe_subprocess(["df", "-T", "--exclude-type=tmpfs", "--exclude-type=devtmpfs", "--output=source,fstype,size,used,avail,pcent,target"])
        
        if "N/D" in output:
            return [{"Error": "Commande 'df' non disponible ou erreur d'exécution."}]

        lines = output.splitlines()
        data = []
        if len(lines) > 1:
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 7:
                    data.append({
                        "target": parts[6], 
                        "fstype": parts[1], 
                        "size": parts[2],
                        "used": parts[3],
                        "available": parts[4],
                        "percent": parts[5],
                    })
        return data

    def get_network_info(self):
        output = _safe_subprocess(["ip", "a"], default_value="N/D")
        
        if "N/D" in output:
            return {"status": "Erreur: Commande 'ip' non disponible.", "interfaces": []}
            
        interfaces = {}
        current_iface = None

        for line in output.splitlines():
            match_iface = re.match(r'^\d+: ([^:]+): <([^>]+)>', line)
            if match_iface:
                current_iface = match_iface.group(1)
                flags = match_iface.group(2)
                status = "UP" if "UP" in flags else "DOWN"
                interfaces[current_iface] = {"status": status, "ip": "N/D"}
                continue

            if current_iface and "inet " in line:
                match_ip = re.search(r'inet (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})', line)
                if match_ip:
                    interfaces[current_iface]["ip"] = match_ip.group(1)

        active_interfaces = [f"{name} ({data['ip']})" for name, data in interfaces.items() if data['status'] == 'UP' and data['ip'] != 'N/D']
        
        return {"status": "Réseau actif" if active_interfaces else "Réseau non actif", "interfaces": active_interfaces}

    def get_web_services(self, ports=[80, 443], host='127.0.0.1'):
        results = {}
        import socket
        
        for port in ports:
            status = "Fermé/N/D"
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                if sock.connect_ex((host, port)) == 0:
                    status = "Ouvert (Service actif)"
                sock.close()
            except Exception:
                status = "Erreur de socket"
            results[port] = status
        return results

def generate_html_report(destination_file):
    collector = SystemCollector()
    script_dir = Path(sys.argv[0]).parent 
    html_template_path = script_dir / "index.html"

    try:
        with open(html_template_path, "r", encoding="utf-8") as f:
            html_template = f.read()
    except FileNotFoundError:
        print(f"Erreur: Le modèle HTML est introuvable à {html_template_path}.")
        sys.exit(1)
        
    data = {
        "general": collector.get_general_info(),
        "memory": collector.get_memory_stats(),
        "temps": collector.get_temperatures(),
        "power": collector.get_power_supply(),
        "processes": collector.get_process_list(),
        "disks": collector.get_disk_usage(),
        "network": collector.get_network_info(),
        "web_services": collector.get_web_services(),
    }
    
    # Remplacements généraux
    html_content = html_template.replace('{{DATE_TEMPS}}', data['general']['time'])
    html_content = html_content.replace('{{HOSTNAME}}', data['general']['hostname'])
    html_content = html_content.replace('{{KERNEL_VERSION}}', data['general']['kernel'])
    html_content = html_content.replace('{{UPTIME}}', data['general']['uptime'])
    
    # Remplacements Mémoire
    mem = data['memory']
    html_content = html_content.replace('{{MEMOIRE_USE_PCT}}', str(mem['used_percent']))
    html_content = html_content.replace('{{MEMOIRE_TOTALE_GO}}', f"{mem['total_gb']} GO")
    html_content = html_content.replace('{{MEMOIRE_USE_PCT_VAL}}', str(mem['used_percent']))
    html_content = html_content.replace('{{MEMOIRE_CACHE_GO}}', f"{mem['cache_gb']} GO")
    html_content = html_content.replace('{{SWAP_USE_PCT}}', str(mem['swap_used_percent']))
    html_content = html_content.replace('{{SWAP_TOTALE_GO}}', f"{mem['swap_total_gb']} GO")
    # LIGNE CRITIQUE : Cette substitution assure le remplissage de la barre
    html_content = html_content.replace('{{SWAP_USE_PCT_VAL}}', str(mem['swap_used_percent'])) 

    # Températures
    temps_html = ""
    if "Erreur" in data['temps']:
        temps_html = f'<li class="message-erreur">{data["temps"]["Erreur"]}</li>'
    else:
        for name, temp in data['temps'].items():
            temps_html += f'<li>{name}: <span class="valeur_temp">{temp}</span></li>'
    html_content = html_content.replace('{{LISTE_TEMPERATURES}}', temps_html)

    # Alimentation
    power = data['power']
    power_status = f"{power['status']} ({power['source']})"
    power_capacity = power['capacity']
    html_content = html_content.replace('{{STATUT_ALIMENTATION}}', power_status)
    html_content = html_content.replace('{{NIVEAU_BATTERIE}}', power_capacity)
    
    # Tableau des Processus
    process_rows = ""
    total_ram_ko = data['memory']['total_gb'] * 1048576 
    if data['processes']:
        for p in data['processes']:
            mem_percent = round((p['mem_ko'] / total_ram_ko) * 100, 1) if total_ram_ko > 0 else 0
            process_rows += f"""
            <tr>
                <td>{p['pid']}</td>
                <td>{p['user']}</td>
                <td>{p['cpu_percent']}</td>
                <td>{mem_percent}%</td>
                <td>{p['name']}</td>
            </tr>
            """
    else:
        process_rows = '<tr><td colspan="5" class="message-erreur" style="text-align:center;">Aucun processus actif ou erreur de lecture.</td></tr>'
    html_content = html_content.replace('{{CORPS_TABLEAU_PROCESSUS}}', process_rows)

    disk_rows = ""
    if 'Error' in data['disks'][0] if data['disks'] else False:
        disk_rows = f'<tr><td colspan="5" class="message-erreur" style="text-align:center;">{data["disks"][0]["Error"]}</td></tr>'
    elif data['disks']:
        for d in data['disks']:
            percent_val = int(d['percent'].replace('%', '').replace('N/A', '0'))
            percent_class = "etat-critique" if percent_val > 90 else "etat-avertissement" if percent_val > 70 else "etat-ok"
            
            disk_rows += f"""
            <tr>
                <td>{d['target']} ({d['fstype']})</td>
                <td>{d['size']}</td>
                <td>{d['used']}</td>
                <td>{d['available']}</td>
                <td class="{percent_class}">{d['percent']}</td>
            </tr>
            """
    else:
        disk_rows = '<tr><td colspan="5" class="message-erreur" style="text-align:center;">Aucun système de fichiers monté ou lisible (df).</td></tr>'
    html_content = html_content.replace('{{CORPS_TABLEAU_DISQUES}}', disk_rows)

    network_list = "".join([f'<li>{i}</li>' for i in data['network']['interfaces']])
    if not network_list:
        network_list = f'<li class="message-erreur">{data["network"]["status"]}</li>'
    html_content = html_content.replace('{{STATUT_RESEAU}}', data['network']['status'])
    html_content = html_content.replace('{{LISTE_INTERFACES}}', network_list)
    html_content = html_content.replace('{{STATUT_PORT_80}}', data['web_services'][80])
    html_content = html_content.replace('{{STATUT_PORT_443}}', data['web_services'][443])
    try:
        with open(destination_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Rapport HTML généré: {destination_file}")
    except IOError as e:
        print(f"Erreur d'écriture: Impossible d'écrire le fichier de rapport à {destination_file}.")
        sys.exit(1)

def interface_graphique():
    
    collector = SystemCollector()
    fenetre = tk.Tk()
    fenetre.title("Surveillance Système (Temps Réel)")
    fenetre.geometry("850x650")
    
    v_heure = tk.StringVar(value="--")
    v_hote = tk.StringVar(value="--")
    v_kernel = tk.StringVar(value="--")
    v_uptime = tk.StringVar(value="--")
    v_ram = tk.StringVar(value="--")
    v_temp = tk.StringVar(value="--")
    v_batterie = tk.StringVar(value="--")
    v_reseau = tk.StringVar(value="--")

    cadre = ttk.Frame(fenetre, padding=12)
    cadre.pack(fill=tk.BOTH, expand=True)
    
    labels_info = [
        ("Heure :", v_heure), ("Nom d'hôte :", v_hote), ("Noyau :", v_kernel),
        ("Uptime :", v_uptime), ("RAM (Usage/Cache/Swap) :", v_ram), 
        ("Températures :", v_temp), ("Alimentation :", v_batterie), ("Réseau (Status/IP) :", v_reseau)
    ]
    
    for i, (text, var) in enumerate(labels_info):
        ttk.Label(cadre, text=text, font=("Segoe UI", 11, "bold")).grid(row=i, column=0, sticky="w", pady=2)
        ttk.Label(cadre, textvariable=var).grid(row=i, column=1, sticky="w", pady=2)

    ttk.Label(cadre, text="Top 30 Processus (par Mémoire) :", font=("Segoe UI", 11, "bold")).grid(row=len(labels_info), column=0, sticky="nw", pady=10)
    zone_processus = tk.Text(cadre, width=80, height=16)
    zone_processus.grid(row=len(labels_info), column=1, sticky="w", pady=10)

    def mise_a_jour():
        try:
            info = collector.get_general_info()
            v_heure.set(info["time"]); v_hote.set(info["hostname"]); v_kernel.set(info["kernel"]); v_uptime.set(info["uptime"])

            mem = collector.get_memory_stats()
            v_ram.set(f"Utilisé: {mem['used_gb']} Go ({mem['used_percent']}%) | Cache: {mem['cache_gb']} Go | Swap: {mem['swap_used_percent']}%")

            temps = collector.get_temperatures()
            temp_str = temps['Erreur'] if "Erreur" in temps else ", ".join([f"{k}: {v}" for k, v in temps.items()])
            v_temp.set(temp_str)

            power = collector.get_power_supply()
            v_batterie.set(f"{power['capacity']} — {power['status']} ({power['source']})")

            net = collector.get_network_info()
            v_reseau.set(f"{net['status']} | Interfaces: {', '.join(net['interfaces']) if net['interfaces'] else 'N/D'}")

            processes = collector.get_process_list()
            zone_processus.delete("1.0", tk.END)
            total_ram_ko = mem['total_gb'] * 1048576

            zone_processus.insert(tk.END, f"{'PID':<6} | {'USER':<10} | {'CPU':<5} | {'MEM':<5} | {'NOM'}\n")
            zone_processus.insert(tk.END, "-" * 75 + "\n")

            for p in processes:
                 mem_percent = round((p['mem_ko'] / total_ram_ko) * 100, 1) if total_ram_ko > 0 else 0
                 zone_processus.insert(tk.END, f"{p['pid']:<6} | {p['user'][:10]:<10} | {p['cpu_percent']:<5} | {str(mem_percent)+'%':<5} | {p['name']}\n")

        except Exception as e:
            messagebox.showerror("Erreur Critique", f"Erreur de mise à jour: {e}")
            fenetre.quit()

        fenetre.after(1500, mise_a_jour) 
    
    mise_a_jour()
    fenetre.mainloop()

def main():
    parser = argparse.ArgumentParser(description="Générateur de rapport d'état système Linux.")
    parser.add_argument("--gui", action="store_true", help="Lance le mode d'interface graphique en temps réel.")
    parser.add_argument("--output", default="rapport_etat_systeme.html", help="Nom du fichier de rapport HTML de sortie.")
    args = parser.parse_args()
    if args.gui:
        interface_graphique()
    else:
        generate_html_report(args.output)





if __name__ == "__main__":
    main()