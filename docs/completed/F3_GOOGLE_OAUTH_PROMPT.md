# F3 — Remplacer l'auth email/password par Google OAuth (seule methode)

## Contexte

Diggy utilise actuellement un systeme email/password + JWT maison. On veut le remplacer **entierement** par Google OAuth — plus de mot de passe, plus de registration manuelle. Google est la SEULE methode d'authentification.

Le premier login Google cree automatiquement le compte. Les logins suivants retrouvent le compte via `google_id`.

Il y a actuellement 2 users en base (admin + 1 user). Ils seront re-crees au premier login Google.

---

## Architecture actuelle a remplacer

### Backend

**`server/api/auth.py`** — A SUPPRIMER entierement
- `hash_password()`, `verify_password()` (bcrypt)
- `create_token()`, `decode_token()` (JWT HS256, 7 jours, env `JWT_SECRET`)

**`server/api/routers/auth.py`** — A REMPLACER
- `POST /api/auth/register` — registration email/password → SUPPRIMER
- `POST /api/auth/login` — login email/password → SUPPRIMER
- `GET /api/auth/me` — retourne le user courant → GARDER
- Schemas `RegisterIn`, `LoginIn` → SUPPRIMER
- Schema `TokenOut` (token, user_id, username, is_admin) → ADAPTER
- Schema `UserOut` (id, email, username, is_active, is_admin, created_at) → GARDER

**`server/api/auth_middleware.py`** — A ADAPTER
- Middleware `JWTAuthMiddleware` qui valide le Bearer token sur les routes protegees
- Routes publiques (GET) : `/api/catalog`, `/api/artists`, `/api/sets`, `/api/genres`, `/api/search`, `/api/taxonomy`
- Routes ouvertes (any method) : `/api/auth/*`, `/api/health`, `/api/docs`, `/api/watchlist/active`
- Logique : extrait `Authorization: Bearer <token>`, appelle `decode_token()` → garder la meme structure mais changer la validation

**`server/api/dependencies.py`** — A ADAPTER
- `get_current_user()` : extrait Bearer token via `HTTPBearer`, decode JWT, lookup User en DB → changer le decode
- `get_current_user_optional()` : idem en soft-mode (None si pas de token)
- `require_admin()` : verifie `user.is_admin` → INCHANGE
- `uid()` : helper → INCHANGE

**`server/api/models.py`** — User model (lignes 48-59)
```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(Text, nullable=False)  # ← SUPPRIMER
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False, server_default="false")
    settings = Column(JSON, default=dict, server_default="{}")
    created_at = Column(DateTime(timezone=True))
```

**`server/api/main.py`** — Monte le middleware et les routers (pas de changement structurel)

### Frontend

**`server/frontend/src/stores/auth.js`** — A REMPLACER
- State : `token` (JWT string), `user` ({id, username, is_admin})
- `login(email, password)` → POST `/api/auth/login` → SUPPRIMER
- `register(email, username, password)` → POST `/api/auth/register` → SUPPRIMER
- `logout()` → clear localStorage → ADAPTER
- `isTokenExpired()` → decode JWT exp claim → SUPPRIMER
- Stockage : `localStorage.diggy_token`, `localStorage.diggy_user`

**`server/frontend/src/views/LoginView.vue`** — A REMPLACER
- Formulaire email/password + toggle login/register
- Appelle `auth.login()` ou `auth.register()`
- Labels en francais ("Connexion", "Email", "Mot de passe", etc.)

**`server/frontend/src/utils/api.js`** — A ADAPTER
- Intercepteur request : injecte `Authorization: Bearer <token>` sur chaque requete
- Intercepteur response : auto-logout sur 401

**`server/frontend/src/router.js`** — A ADAPTER
- Routes publiques : `/` (HubView, `meta: { public: true }`), `/login` (LoginView)
- Guard : `if (!to.meta.public && !auth.isAuthenticated) return '/'`

**`server/frontend/src/components/SidebarNav.vue`** — A ADAPTER
- Affiche username + bouton logout si authentifie
- Affiche lien "Connexion" sinon

### Tests

**`tests/api/conftest.py`** — fixtures `auth_user` et `admin_user` creent des User avec `hash_password("testpass")`
**`tests/api/test_auth.py`** — tests register/login/me
**`tests/api/test_auth_module.py`** — tests hash_password/verify_password/create_token/decode_token
**`tests/api/test_auth_middleware.py`** — tests middleware public/protected routes

### Dependencies actuelles (a retirer)
```
python-jose[cryptography]==3.3.0
bcrypt==4.2.1
```

### Variables d'env actuelles
- `JWT_SECRET` (VPS `.env`) — a supprimer

---

## Ce qu'il faut implementer

### Flow Google OAuth

1. **Frontend** : bouton "Se connecter avec Google" → redirige vers `https://accounts.google.com/o/oauth2/v2/auth` avec `client_id`, `redirect_uri`, `scope=openid email profile`
2. **Google** : l'utilisateur consent → redirige vers `redirect_uri` avec un `code`
3. **Backend** : echange le `code` contre un `id_token` via `https://oauth2.googleapis.com/token`
4. **Backend** : valide le `id_token`, extrait `sub` (google_id), `email`, `name`
5. **Backend** : lookup User par `google_id` → si pas trouve, cree le compte automatiquement
6. **Backend** : genere un JWT interne (on garde un JWT simple pour les appels API, mais genere a partir du login Google, pas d'un password)
7. **Frontend** : recoit le JWT + user info, stocke en localStorage, redirige vers `/`

### Nouveaux endpoints backend

```
GET  /api/auth/google/login     → retourne l'URL d'autorisation Google (avec state CSRF)
GET  /api/auth/google/callback  → echange le code, cree/retrouve le user, retourne TokenOut
GET  /api/auth/me               → inchange
```

### Google Cloud Console

- Creer un projet Google Cloud (ou utiliser un existant)
- APIs & Services → Credentials → Create OAuth 2.0 Client ID
- Application type : Web application
- Authorized redirect URIs : `https://diggy-music.fr/api/auth/google/callback`
- Recuperer `GOOGLE_CLIENT_ID` et `GOOGLE_CLIENT_SECRET`

### Nouvelles variables d'env

```env
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx
# JWT_SECRET reste (pour signer les JWT internes post-login)
```

### Migration DB (Alembic 0024)

```python
# 1. Ajouter google_id + picture_url
op.add_column("users", sa.Column("google_id", sa.String(255), unique=True, nullable=True))
op.add_column("users", sa.Column("picture_url", sa.Text, nullable=True))

# 2. Rendre hashed_password nullable (transition)
op.alter_column("users", "hashed_password", nullable=True)

# 3. Dans un second temps (apres migration des users) : drop hashed_password
```

Note : ne pas dropper `hashed_password` dans la meme migration — laisser nullable d'abord, dropper plus tard.

### Model User modifie

```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    google_id = Column(String(255), unique=True, nullable=True)  # NOUVEAU
    picture_url = Column(Text, nullable=True)                     # NOUVEAU
    hashed_password = Column(Text, nullable=True)                 # nullable puis drop
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False, server_default="false")
    settings = Column(JSON, default=dict, server_default="{}")
    created_at = Column(DateTime(timezone=True))
```

### Backend : nouveau `auth.py`

Garder `create_token()` et `decode_token()` (JWT interne). Supprimer `hash_password()` et `verify_password()`. Ajouter :

```python
async def verify_google_token(code: str) -> dict:
    """Echange le code Google contre un id_token, retourne les infos user."""
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        token_data = resp.json()

    # Valider l'id_token
    from google.oauth2 import id_token
    from google.auth.transport import requests
    id_info = id_token.verify_oauth2_token(
        token_data["id_token"], requests.Request(), GOOGLE_CLIENT_ID
    )
    return {
        "google_id": id_info["sub"],
        "email": id_info["email"],
        "name": id_info.get("name", id_info["email"].split("@")[0]),
        "picture": id_info.get("picture"),
    }
```

### Backend : nouveau `routers/auth.py`

```python
@router.get("/google/login")
async def google_login():
    """Retourne l'URL d'autorisation Google."""
    state = secrets.token_urlsafe(32)
    # Stocker state en cache/session pour validation CSRF
    params = urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    })
    return {"url": f"https://accounts.google.com/o/oauth2/v2/auth?{params}", "state": state}


@router.get("/google/callback")
async def google_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    """Echange le code, cree/retrouve le user, retourne le JWT."""
    google_info = await verify_google_token(code)

    # Lookup par google_id
    result = await db.execute(select(User).where(User.google_id == google_info["google_id"]))
    user = result.scalar_one_or_none()

    if not user:
        # Premiere connexion : creer le compte
        username = google_info["name"].replace(" ", "").lower()[:50]
        # Gerer les doublons de username...
        user = User(
            email=google_info["email"],
            username=username,
            google_id=google_info["google_id"],
            picture_url=google_info.get("picture"),
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_token(user.id)
    # Redirect vers le frontend avec le token en query param
    return RedirectResponse(f"/?token={token}&user_id={user.id}&username={user.username}&is_admin={user.is_admin}")


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
```

### Frontend : nouveau `LoginView.vue`

```vue
<template>
  <div class="login-card">
    <div class="brand">
      <span class="glyph">D</span>
      <span class="name">Diggy</span>
    </div>
    <button class="google-btn" @click="loginWithGoogle" :disabled="loading">
      <GoogleIcon />
      Se connecter avec Google
    </button>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>
```

### Frontend : nouveau `stores/auth.js`

```javascript
// login() → redirige vers Google
async function loginWithGoogle() {
  const res = await fetch('/api/auth/google/login')
  const { url } = await res.json()
  window.location.href = url  // redirect vers Google
}

// Au retour du callback, le frontend intercepte le token dans l'URL
// (dans App.vue ou router guard)
function handleCallback() {
  const params = new URLSearchParams(window.location.search)
  const token = params.get('token')
  if (token) {
    _persist(token, { id: params.get('user_id'), username: params.get('username'), is_admin: params.get('is_admin') === 'True' })
    router.replace('/')  // nettoie l'URL
  }
}
```

### Dependencies a ajouter

```
google-auth>=2.0
```

### Dependencies a retirer

```
bcrypt==4.2.1
# python-jose reste (on garde les JWT internes)
```

### Tests a adapter

- **conftest.py** : les fixtures `auth_user`/`admin_user` ne hashent plus de password, mettent un `google_id` a la place
- **test_auth.py** : tester le callback Google (mocker `verify_google_token`), tester `/me`
- **test_auth_module.py** : supprimer tests hash/verify password, garder tests JWT
- **test_auth_middleware.py** : inchange (meme Bearer token, meme middleware)

---

## Fichiers a modifier (exhaustif)

| Fichier | Action |
|---------|--------|
| `server/api/auth.py` | Supprimer hash/verify password, garder JWT, ajouter `verify_google_token()` |
| `server/api/routers/auth.py` | Supprimer register/login, ajouter google/login + google/callback |
| `server/api/models.py` | Ajouter `google_id`, `picture_url`, rendre `hashed_password` nullable |
| `server/api/dependencies.py` | Inchange (garde Bearer JWT) |
| `server/api/auth_middleware.py` | Inchange (garde Bearer JWT) |
| `server/api/main.py` | Inchange |
| `server/api/requirements.txt` | Ajouter `google-auth`, retirer `bcrypt` |
| `server/api/alembic/versions/0024_*.py` | Migration google_id + hashed_password nullable |
| `server/frontend/src/stores/auth.js` | Remplacer login/register par loginWithGoogle + handleCallback |
| `server/frontend/src/views/LoginView.vue` | Remplacer formulaire par bouton Google |
| `server/frontend/src/router.js` | Ajouter interception du callback (token dans URL) |
| `server/frontend/src/utils/api.js` | Inchange (garde Bearer) |
| `server/frontend/src/components/SidebarNav.vue` | Inchange (garde logout) |
| `tests/api/conftest.py` | Adapter fixtures (google_id au lieu de password) |
| `tests/api/test_auth.py` | Tester callback Google (mock) |
| `tests/api/test_auth_module.py` | Supprimer tests password |
| `.env` (VPS) | Ajouter GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET |

## Infos deploy

- Domaine : `diggy-music.fr` (HTTPS, Let's Encrypt)
- Redirect URI Google : `https://diggy-music.fr/api/auth/google/callback`
- Nginx proxie `/api/*` vers `http://api:8000` (pas de changement nginx)
- `.env` uniquement sur le VPS (`/root/diggy/.env`), jamais dans git

## Conventions du projet

- Code en anglais, UI en francais
- Zero couleur hardcodee dans le frontend, tout via `var(--...)` depuis `diggy-tokens.css`
- Commits : `feat(auth):`, `fix(auth):`, etc.
- Tests avec pytest + SQLite (local) / PostgreSQL (CI)
- Modulaire, blocs simples, fichiers courts
