# ASTUM ML - Dashboard Utilidad Vendedores MercadoLibre

SaaS multi-cliente para que vendedores de MercadoLibre vean la utilidad real de sus productos (restando costos, comisiones ML y envío).

## 📦 Archivos

| Archivo | Qué es |
|---|---|
| `app_saas.py` | App principal (login + dashboard) |
| `database.py` | Base de datos SQLite (usuarios, tokens, costos) |
| `requirements.txt` | Dependencias Python |
| `saas_ml.db` | Base de datos (se crea sola al iniciar) |

## 🚀 Subir a Streamlit Cloud

1. **Crear repositorio en GitHub**
   - Ve a https://github.com/new
   - Crea un repositorio PRIVADO
   - Sube estos 3 archivos: `app_saas.py`, `database.py`, `requirements.txt`

2. **Conectar con Streamlit Cloud**
   - Entra a https://share.streamlit.io
   - Inicia sesión con tu cuenta de GitHub
   - Click en "New app" → conecta tu repositorio
   - Rama: `main` / Archivo: `app_saas.py`
   - Click en "Deploy"

3. **¡Listo!**
   - En 2-3 minutos tendrás tu app online
   - URL: `https://[tu-nombre]-[repo].streamlit.app`

## 💻 Correr local (en Windows)

```bash
pip install -r requirements.txt
streamlit run app_saas.py
```

Abrir en el navegador: http://localhost:8501

## ⚠️ Importante

**Streamlit Cloud usa SQLite que es efímero.** Los datos se pierden al reiniciar la app. Para un servicio real, migrar a PostgreSQL (Supabase tiene plan gratis).

## 🔜 Próximos pasos

- Conexión a MercadoLibre por usuario (OAuth)
- Carga de CSV de costos
- Dashboard con datos reales
- Refresco automático de token
