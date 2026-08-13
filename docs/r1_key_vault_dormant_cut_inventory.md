# Inventario exacto del corte R1 Key Vault dormido v0.551

Estado: `REMOTE-REF-PUBLISHED-VERIFIED`.

Base desplegada: commit `41ab2d5435cadf22db60574166d7eb29dd1dd57e`,
árbol `370a5b4e5b2b55420e0c918fa8dfc12c6bd42b30`.

El payload canónico Git contiene 17 rutas y 114575 bytes. No contiene workflows, documentos
vivos, credenciales, App Settings, scripts de operación ni utilidades del
candidato anterior. Cada línea canónica usa `ruta|bytes|SHA-256`, UTF-8, LF y
salto final. Su SHA-256 agregado es
`AC8B7F74EAF961E3393BE258404B94728609B34B9B4FCE25C036BACCAFE33151`.

```text
requirements.txt|314|F1E0920C62DDE427C43FBAA9B851CC651C23E6C4FF001A716C4FB65312A31626
bitrix_connector/r1_pre_event_activation_preflight.py|5549|3A85F68BF2514A4A43262CB250106C256A63E3B1C105FEBB3FC7985E2172D2FE
bitrix_connector/r1_pre_event_activation_evidence_collector.py|9726|D9A083DB22644F5C8DC77BF7CC1C15B435134B42BE6CCF9CB31D7C1D8AB1A4CB
bitrix_connector/r1_pre_event_activation_exact_switch_reader.py|3760|9095209A9B1254FF78CA438A75D3214F8FB79C6F5C9DD9405BEFA235CF35AE29
bitrix_connector/r1_pre_event_activation_real_binding.py|5065|3F44572127B471C132D299068CCD6BCDFF6271E2ADA0FDFD7629D503B769A46C
bitrix_connector/r1_pre_event_activation_operation_contract.py|8506|7C1259F476767B35AD472818738744910C9A9415B4DA0E82C539BAE0BBBE8270
bitrix_connector/r1_pre_event_activation_compound_owner.py|11384|3469C8A5595BDCEB4045B11C58B95B5BD09F6DD1CA8CC0715FF033FCBC32CA00
bitrix_connector/r1_key_vault_exact_secret_backend.py|12736|7B4174F28F764A13ABF9A63B8C803E0F95C60EB2F5D4D12BD95122996DC40337
bitrix_connector/r1_key_vault_url_exact_reader.py|3826|B5989AAF3A1D03FA1FD417EEE56B69F35E6FA054F407B58A15284FB93ACB5B0A
tests/test_r1_pre_event_activation_preflight.py|6835|D7299F68727EF86FE1F1609673CCCF403FB55FFB72BDF92243FF18BC92ADFEF3
tests/test_r1_pre_event_activation_evidence_collector.py|7525|A32243B0D7A94EEEFBA12337796B43A07477A29D3049B3782CFD840620571540
tests/test_r1_pre_event_activation_exact_switch_reader.py|4146|1E6E1B2D1FB5284D489A89E91641DA8BE46693397D7913DB4A8AB07F46CCA06D
tests/test_r1_pre_event_activation_real_binding.py|7472|96870C5D98C0D65290A7C2E155C0F71ECADF6B1913E53FAD983C2893E406A67E
tests/test_r1_pre_event_activation_operation_contract.py|7053|ECB262AC6C6F4470C656B80FE11C361C0D1D6D590033973F8E1D87C94FD8BA8F
tests/test_r1_pre_event_activation_compound_owner.py|6898|E13622CA595DEE65D4C1D5105E3C00380F24CA67BE98CE2128B569F9EE267593
tests/test_r1_key_vault_exact_secret_backend.py|9116|E1372654BEB1CAF5DF1B637F8475263DAFD5BF52D3F185CE9BFB7D7514A7FB44
tests/test_r1_key_vault_url_exact_reader.py|4664|FD33129AD42769276C91FF6CA3616BC977092DDF7D8544B32F1DCD9CD6EE6038
```

Todo archivo ausente, adicional, con tamaño/hash distinto o cambio de la base
invalida el corte. Los documentos de control describen el corte pero no forman
parte del payload desplegable y no alteran su huella.

## Validación aislada

Un clon local temporal independiente, sin red ni hardlinks, reprodujo el árbol
base exacto. Tras normalizar `requirements.txt` a LF según la política Git y
superponer sólo el payload produjo el árbol candidato
`7214bbb08ded045d59b6eb7ea0710b6fc68c18f8`, 17 rutas y cero workflows.
Pruebas de activación 48/48, Key Vault 21/21 y suite completa del corte
1685/1685: `PASS`. El temporal fue eliminado y no creó objetos, índice o refs en
el repositorio original.

El commit candidato local
`e6af8b390f401dd3f2934faf2ced3ed70002e7bf` tiene un solo padre, la base exacta,
y el árbol canónico anterior. La postlectura confirmó 17 rutas, cero workflows,
cero refs apuntándolo e índice/refs/worktree compartidos sin cambios.

La ref remota `codex/r1-keyvault-dormant-v0551` fue publicada una vez y
convergió en la primera observación sobre el SHA exacto. `main` permaneció en la
base, el candidato tuvo cero Actions y no se ejecutó rollback ni se creó PR.
