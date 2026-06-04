import subprocess, datetime
Import("env")

def _git(args, default):
    try:
        return subprocess.check_output(["git"] + args, cwd=env["PROJECT_DIR"],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return default

rev = _git(["rev-parse", "--short=8", "HEAD"], "nogit")
dirty = "-dirty" if _git(["status", "--porcelain"], "") else ""
date = datetime.datetime.now().strftime("%Y-%m-%d")

env.Append(CPPDEFINES=[("FW_REV", env.StringifyMacro(rev + dirty)),
                       ("FW_BUILD_DATE", env.StringifyMacro(date))])

print("gen_version: FW_REV=%s%s FW_BUILD_DATE=%s" % (rev, dirty, date))
