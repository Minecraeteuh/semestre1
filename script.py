import time,socket,platform,subprocess, glob


heure=time.strftime(("%H:%M:%S"))


nom_machine=socket.gethostname()


version_linux=platform.system()+" "+platform.release()


uptime=float(open("/proc/uptime").read().split()[0])
uptime_propre=(f"{int(uptime//3600)}h {int((uptime%3600)//60)}min {uptime%60:.0f}sec")


def get_temperatures():

    temperatures = {}
    zone_paths = glob.glob("/sys/class/thermal/thermal_zone*")

    if not zone_paths:
        return {"erreur": "Aucun capteur de température trouvé dans /sys/class/thermal/."}
    for path in zone_paths:
        try:
            with open(path + "/type", 'r') as f_type:
                type_name = f_type.read().strip()
            with open(path + "/temp", 'r') as f_temp:
                temp_value_str = f_temp.read().strip()
            temp_celsius = int(temp_value_str) / 1000.0
            temperatures[type_name] = f"{temp_celsius:.1f}°C"
        except (FileNotFoundError, PermissionError, ValueError, OSError) as e:
            try:
                type_name = path.split('/')[-1] + "_type_inconnu"
            except Exception:
                type_name = path

            temperatures[type_name] = f"Erreur de lecture : {e}"

    return temperatures
temp_composants = get_temperatures()

def get_gpu_temperature():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, encoding='utf-8'
        )
        return f"{int(result.stdout.strip())}°C"
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    except Exception as e:
        return f"Erreur GPU: {e}"
gpu_temp = get_gpu_temperature()
if gpu_temp:
    temp_composants["GPU_NVIDIA"] = gpu_temp
#CPU=0 chipset=1 GPU=gpu_temperature()


alimentation=[open("/sys/class/power_supply/BAT1/type").read().strip(),open("/sys/class/power_supply/BAT1/status").read().strip(),open("/sys/class/power_supply/BAT1/capacity").read().rstrip("\n"),open("/sys/class/power_supply/BAT1/charge_now").read().rstrip("\n"),open("/sys/class/power_supply/BAT1/charge_full").read().rstrip("\n")]
#batterie=0   status_de_charge=1   pourcentage=2   capacité_actuelle=3   capacité_max=4       les capacités sont en microampères-heure donc /6 pour avoir en ampère-heure


fichiermeminfo = open("/proc/meminfo").read().splitlines()
total = int([l for l in fichiermeminfo if l.startswith("MemTotal:")][0].split()[1])
available = int([l for l in fichiermeminfo if l.startswith("MemAvailable:")][0].split()[1])
used = total - available
ram_info = [round(total / 1048576, 1), round(used / 1048576, 1), round(available / 1048576, 1)]


def get(p):
    return open(p).read().strip()
disk_info = [get(f"/sys/block/nvme0n1/device/model"),round(int(get(f"/sys/block/nvme0n1/size")) * 512 / 1000000000, 2),"SSD/NVMe" if get(f"/sys/block/nvme0n1/queue/rotational") == "0" else "HDD"]
# 0=nom du modèle 1=Taille en Go 2=Type de disque



processus = []
for path in glob.glob("/proc/[0-9]*/status"):
    try:
        lignes = open(path).read().splitlines()
        pid = path.split("/")[2]
        nom = [l.split(":")[1].strip() for l in lignes if l.startswith("Name:")][0]
        uid = [l.split(":")[1].split()[0] for l in lignes if l.startswith("Uid:")][0]
        mem = [l.split(":")[1].split()[0] for l in lignes if l.startswith("VmRSS:")]
        mem = int(mem[0]) if mem else 0

        stat_path = f"/proc/{pid}/stat"
        stat_values = open(stat_path).read().split()
        utime = int(stat_values[13])
        stime = int(stat_values[14])
        cpu_time = round((utime + stime) / 2)

        processus.append((nom, pid, uid, mem))
    except Exception:
            print("Erreur infos processus")




def get_wifi_info():
    try:
        result=subprocess.run(['iwgetid','-r'],capture_output=True,text=True,check=True,encoding='utf-8')
        ssid=result.stdout.strip()

        if ssid:
            return "Le nom du wifi est "+ ssid
        else:
            return "Non connecté a un réseau wifi"
    except:
        return "Erreur : vous n'êtes probablement pas connecté sur un réseau wifi   ."


dl_info=[open("/sys/class/net/wlp8s0/statistics/rx_bytes").read(),open("/sys/class/net/wlp8s0/statistics/tx_bytes").read()]
dl1=dl_info[0].strip(),dl_info[1].strip()
telechargement=str(int(int(dl1[0])/1000024)) + ("Mo")
envoi=int(dl1[1])/1024
