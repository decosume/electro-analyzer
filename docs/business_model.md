# Digital Monk – Modelos de negocios para playlists premium

## 1. Producto

### Portafolio curado por vertical
- **Barberías:** soul/funk/rock con bloques mañana–tarde–noche.
- **Restaurantes mexicanos:** brunch acústico, lunch enérgico, cenas lounge.
- **Gimnasios:** warm-up, high-intensity, cool-down.
- Incluye rotación manual semanal (miércoles) y campañas especiales (festivos, promos).

### Perfiles personalizados
- Brief rápido (tipo de negocio, horarios, idiomas, edad del público).
- Generamos `profile.json` exclusivo + reporte PDF (tono, recomendaciones de audio, URL).
- Playlist publicada en la cuenta Spotify del cliente (se mantiene ownership).

### Extras premium
- Reporte mensual con highlights (temas nuevos, duración, mood).
- Assets para marketing: QR, artes para redes, textos sugeridos.
- Supervisión on-site / soporte técnico (volumen, configuración de bocinas).

## 2. Operación
1. **Onboarding** (30 min): cuestionario + moodboard del cliente.
2. **Curaduría** (2–3 días): usamos `scripts/build_client_profile.py` + ajustes manuales, validación en Spotify.
3. **Entrega**: playlist + reporte en PDF + instrucciones de reproducción (volumen recomendado, zonas).
4. **Mantenimiento**:
   - Refresh semanal automatizado (`cron` o recordatorio).
   - Cambios ad-hoc (eventos) con cargo extra.
   - Soporte continuo: resolución de tokens, rate limits, cambios de perfil.

**Stack interno**
- Repositorio Git (perfiles, librerías de moods, scripts).
- Caché de IDs para minimizar llamadas a la API.
- Cronjobs/recordatorios para garantizar puntualidad.

## 3. Precios sugeridos (USD/mes)
| Plan      | Incluye                                                                 | Precio |
|-----------|-------------------------------------------------------------------------|-------:|
| Starter   | Playlist base por vertical + refresh semanal + reporte mensual básico   | 149    |
| Premium   | Playlist personalizada, 2 variaciones (día/noche), assets QR, soporte prioritario | 349    |
| Enterprise| Hasta 3 locales, campañas ilimitadas, métricas detalladas, visitas on-site | 699+ |

Extras:
- Campaña o evento temático: USD 99 cada uno.
- Integraciones especiales (digital signage, dashboards) o consultoría in situ: bajo cotización.

## 4. Pitch de valor
- **Curaduría humana + automatización:** narrativa musical diseñada por expertos, con infraestructura que asegura updates puntuales.
- **Control total del contenido:** IDs guardados localmente, sin depender de recomendaciones aleatorias.
- **Experiencia medible:** bloques por horario, balance actual/clásicos, recomendaciones de audio para reproducir correctamente.

## Próximos pasos
1. Preparar one-pager comercial y versión PDF de reportes (branding Digital Monk).
2. Configurar cronjobs por cliente (perfil + `electro playlist`) y monitoreo simple.
3. Armar paquetes de onboarding (brief template, checklist de audio, ejemplos de campañas).

> Digital Monk: playlists curadas como servicio, listas para vender a negocios que buscan una experiencia sonora premium.
