import grp
import pwd

from fastapi import APIRouter, Depends, Form, Request

from ..system import run_helper
from ..web import csrf_protect, current_user, render, result

router = APIRouter(dependencies=[Depends(current_user), Depends(csrf_protect)])


def list_users():
    members = {}
    for g in grp.getgrall():
        for m in g.gr_mem:
            members.setdefault(m, []).append(g.gr_name)
    users = []
    for p in sorted(pwd.getpwall(), key=lambda p: p.pw_uid):
        if p.pw_uid < 1000 or p.pw_uid == 65534:
            continue
        groups = sorted(members.get(p.pw_name, []))
        users.append({
            "name": p.pw_name,
            "uid": p.pw_uid,
            "full": p.pw_gecos.split(",")[0],
            "home": p.pw_dir,
            "shell": p.pw_shell,
            "groups": groups,
            "admin": bool({"sudo", "admin", "wheel"} & set(groups)),
        })
    return users


@router.get("/users")
async def users_page(request: Request):
    return render(request, "users.html", page="users", title="Användare", users=list_users())


@router.get("/users/table")
async def users_table(request: Request):
    return render(request, "_users_table.html", users=list_users())


@router.post("/users")
async def create_user(request: Request, username: str = Form(...), password: str = Form(...),
                      sudo: bool = Form(False)):
    if "\n" in password or not password:
        return result(request, False, "Ogiltigt lösenord")
    args = [username, "sudo"] if sudo else [username]
    rc, out = await run_helper("user-add", *args, input=password + "\n")
    return result(request, rc == 0,
                  f"Användaren {username} skapades" if rc == 0 else "Kunde inte skapa användaren", out)


@router.post("/users/{username}/delete")
async def delete_user(request: Request, username: str, user: str = Depends(current_user)):
    if username == user:
        return result(request, False, "Du kan inte ta bort dig själv")
    rc, out = await run_helper("user-del", username)
    return result(request, rc == 0,
                  f"Användaren {username} togs bort" if rc == 0 else "Kunde inte ta bort användaren", out)
