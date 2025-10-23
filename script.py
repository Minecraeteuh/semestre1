import time,socket,platform,subprocess, glob


heure=time.strftime(("%H:%M:%S"))


nom_machine=socket.gethostname()


version_linux=platform.system()+" "+platform.release()


uptime=float(open("/proc/uptime").read().split()[0])
uptime_propre=(f"{int(uptime//3600)}h {int((uptime%3600)//60)}min {uptime%60:.0f}sec")


def gpu_temperature():
    output = subprocess.check_output(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"])
    return int(output.strip())
gpu_temp = str(gpu_temperature()) + "°C"
temp_composants=[open("/sys/class/thermal/thermal_zone2/temp").read().strip(),open("/sys/class/thermal/thermal_zone2/temp").read().strip()]
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
        processus.append((pid, uid, mem, nom))
    except Exception:
        pass

print(processus)