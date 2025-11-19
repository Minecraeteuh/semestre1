import time
import socket
import platform
import subprocess
import glob
import sys
import pprint  # Utilisé uniquement pour l'affichage de fin


# --- 1. FONCTION UTILITAIRE (Gestion des erreurs de lecture) ---
def lire_fichier(chemin):
    """Lit un fichier proprement sans faire crasher le programme."""
    try:
        # Utilisation de 'with open' pour s'assurer que le fichier est fermé
        with open(chemin, 'r') as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError, OSError):
        # Retourne None en cas d'échec (lecture illisible, fichier manquant, etc.)
        return None


# --- 2. FONCTIONS DE COLLECTE ROBUSTES ---

def get_infos_generales():
    """Récupère date, hostname, kernel et uptime."""
    uptime_brut = lire_fichier("/proc/uptime")
    uptime_sec = float(uptime_brut.split()[0]) if uptime_brut else 0

    # Formatage de l'uptime
    heures = int(uptime_sec // 3600)
    minutes = int((uptime_sec % 3600) // 60)
    secondes = int(uptime_sec % 60)

    return {
        "date_heure": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": socket.gethostname(),
        "kernel": f"{platform.system()} {platform.release()}",
        "uptime_format": f"{heures}h {minutes}min {secondes}s",
        "uptime_sec": uptime_sec
    }


def get_cpu_gpu_temp():
    """Récupère dynamiquement les températures (CPU & GPU)."""
    temps = {}

    # CPU / Système (Via sysfs)
    for path in glob.glob("/sys/class/thermal/thermal_zone*"):
        nom = lire_fichier(f"{path}/type") or path.split('/')[-1]  # Utilise le nom du dossier si type non trouvé
        val = lire_fichier(f"{path}/temp")
        if val and val.isdigit():
            temps[nom] = f"{int(val) / 1000:.1f}°C"

    # GPU NVIDIA (Via subprocess, sécurisé)
    try:
        res = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, check=True)
        temps["GPU_NVIDIA"] = f"{res.stdout.strip()}°C"
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Ajout d'une entrée claire si le GPU est manquant ou si la commande échoue
        temps["GPU_NVIDIA"] = "Non détecté ou commande nvidia-smi manquante"
    except Exception as e:
        temps["GPU_NVIDIA"] = f"Erreur de lecture: {e}"

    return temps


def get_alimentation():
    """Détecte dynamiquement la batterie ou l'alimentation secteur."""
    alim_info = {}

    # Cherche tout ce qui ressemble à BAT* ou AC*
    for path in glob.glob("/sys/class/power_supply/*"):
        nom_device = path.split('/')[-1]

        if not (nom_device.startswith('BAT') or nom_device.startswith('AC')):
            continue

        status = lire_fichier(f"{path}/status")
        capacity_percent = lire_fichier(f"{path}/capacity")
        charge_now = lire_fichier(f"{path}/charge_now")
        charge_full = lire_fichier(f"{path}/charge_full")

        # Traitement pour les batteries
        if nom_device.startswith('BAT') and status:
            cap_now = int(charge_now) if charge_now and charge_now.isdigit() else 0
            cap_full = int(charge_full) if charge_full and charge_full.isdigit() else 1

            alim_info[nom_device] = {
                "etat": status,
                "pourcentage": f"{capacity_percent}%" if capacity_percent else "N/A",
                "cap_actuelle_mah": f"{cap_now / 1000:.0f} mAh",
                "cap_max_mah": f"{cap_full / 1000:.0f} mAh"
            }

        # Traitement pour l'AC (secteur)
        elif nom_device.startswith('AC'):
            present = lire_fichier(f"{path}/online")
            alim_info[nom_device] = "Connecté" if present == "1" else "Déconnecté"

    if not alim_info:
        return {"etat_global": "Aucune source d'alimentation détectée"}
    return alim_info


def get_memoire():
    """Calcul simple et robuste de la RAM (total, utilisée, libre en pourcentage et Go)."""
    meminfo = lire_fichier("/proc/meminfo")
    if not meminfo:
        return {"erreur": "Impossible de lire /proc/meminfo"}

    try:
        lignes = meminfo.splitlines()
        # Conversion des valeurs KiB en Octets, puis en GiB (Go)
        get_val = lambda label: int([x for x in lignes if label in x][0].split()[1]) * 1024

        total = get_val("MemTotal")
        dispo = get_val("MemAvailable")
        utilise = total - dispo

        return {
            "total_go": round(total / (1024 ** 3), 1),
            "utilise_go": round(utilise / (1024 ** 3), 1),
            "pourcentage_utilise": round((utilise / total) * 100, 1)
        }
    except Exception as e:
        return {"erreur": f"Erreur lors de l'analyse de la mémoire: {e}"}


def get_stockage():
    """Scanne tous les disques physiques, remplace 'nvme0n1'."""
    disques = {}
    patterns = ["/sys/block/sd*", "/sys/block/nvme*", "/sys/block/mmcblk*"]
    chemins = []
    for p in patterns: chemins.extend(glob.glob(p))

    for path in chemins:
        nom_disque = path.split('/')[-1]

        # Ignorer les partitions (sda1, sda2)
        if len(nom_disque) > 3 and nom_disque[-1].isdigit(): continue

        modele = lire_fichier(f"{path}/device/model") or "Inconnu"
        taille_sec = lire_fichier(f"{path}/size")
        taille_go = 0
        if taille_sec and taille_sec.isdigit():
            taille_go = round((int(taille_sec) * 512) / (1000 ** 3), 1)

        rot = lire_fichier(f"{path}/queue/rotational")
        type_d = "HDD" if rot == "1" else "SSD/NVMe"

        disques[nom_disque] = f"{modele} ({taille_go} Go) - {type_d}"

    if not disques:
        return {"erreur": "Aucun périphérique de stockage détecté."}
    return disques


def get_reseau():
    """Récupère les statistiques RX/TX pour toutes les interfaces et le SSID WiFi."""
    net_info = {}

    # 1. Statistiques de base (RX/TX)
    for path in glob.glob("/sys/class/net/*"):
        iface = path.split('/')[-1]
        if iface == "lo": continue

        rx = lire_fichier(f"{path}/statistics/rx_bytes")
        tx = lire_fichier(f"{path}/statistics/tx_bytes")

        # Conversion propre en MiB (Mégaoctets binaires)
        rx_mib = round(int(rx) / (1024 ** 2), 1) if rx and rx.isdigit() else 0
        tx_mib = round(int(tx) / (1024 ** 2), 1) if tx and tx.isdigit() else 0

        net_info[iface] = {"DL_MiB": rx_mib, "UL_MiB": tx_mib}

    # 2. Info Wifi spécifique (SSID)
    try:
        res = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True, check=False)
        ssid = res.stdout.strip()
        net_info["WIFI_SSID"] = ssid if ssid else "Non connecté"
    except FileNotFoundError:
        net_info["WIFI_SSID"] = "Commande iwgetid manquante"
    except Exception as e:
        net_info["WIFI_SSID"] = f"Erreur de lecture: {e}"

    return net_info


# --- 3. FONCTION D'ORCHESTRATION ---
def collecter_toutes_les_metriques():
    """Appelle toutes les fonctions pour centraliser la collecte."""

    # Les processus sont le point le plus lent, donc on les met à part pour l'instant
    # (Ils devront être refactorisés pour le calcul CPU)
    # process_list = get_process_list()

    return {
        "General": get_infos_generales(),
        "Temperatures": get_cpu_gpu_temp(),
        "Memoire": get_memoire(),
        "Alimentation": get_alimentation(),
        "Disques": get_stockage(),
        "Reseau": get_reseau()
        # "Processus": process_list
    }

print(get_reseau())