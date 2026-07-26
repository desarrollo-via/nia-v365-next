# Plantilla inerte de despliegue G0 — supersedida

La decisión vigente es alojar `bitrix_connector` como módulo independiente y
apagable dentro de `nia-v365-next-api`, sin crear otro recurso. Consulte
`docs/bitrix_connector_embedded_topology.md`.

Esta plantilla se conserva únicamente como evidencia histórica y no debe
copiarse, activarse ni adaptarse para producción.

`g0-azure-webapp.yml.example` es documentacion ejecutable futura, pero no es un
workflow activo: permanece deliberadamente fuera de `.github/workflows`.

Antes de considerar su activacion deben existir y verificarse, con
autorizaciones independientes:

- un Azure Web App exclusivo para G0, cuyo nombre no sea `nia-v365`;
- el hostname HTTPS estable que alimentara `NIA_BITRIX_G0_PUBLIC_ORIGIN`;
- una identidad OIDC exclusiva y de alcance minimo;
- las variables seguras de plataforma descritas en
  `docs/bitrix_g0_deployment_topology.md`;
- el startup `python -m bitrix_connector.g0_deployment`;
- exactamente una instancia, un proceso y un worker.

La plantilla exige la confirmacion literal `DESPLEGAR G0 OFF`, no tiene trigger
por `push`, usa nombre y origen suministrados como variables y rechaza
explicitamente `nia-v365`. Empaqueta solo `bitrix_connector/` y
`requirements.txt`; no incluye `main.py`, `.env`, pruebas ni documentos.

Copiar o mover esta plantilla a `.github/workflows`, crear recursos, cargar
secretos, hacer commit/push, ejecutar el workflow o desplegar son acciones
separadas y no quedan autorizadas por la existencia de este archivo.
