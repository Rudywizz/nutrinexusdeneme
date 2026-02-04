# NutriNexus — Sprint 4.0 (Klinik Zeka)

Bu paket, Sprint 3.9.3 kurumsal UI üzerine **Sprint 4.0 Klinik Zeka** ekler:
- Kan tahlili için **kural tabanlı yorum önerileri**
- Ölçüm trendi için **uyarılar**
- Klinik Kart > Özet içinde **tek bakış Klinik Özet** (son ölçüm + son tahlil + trend + klinik zeka paneli)

> Not: Öneriler tıbbi cihaz değildir; klinik karar yerine geçmez.

Bu sürümde amaç: **Danışan CRUD** sağlam kaldıktan sonra, danışan detayı içinde **Klinik Kart iskeletini** gerçek veriyle çalışır hale getirmek.

## Sprint-2 Kapsam
- Danışan Detay: **Genel Bilgiler + Düzenle**
- Klinik Kart > **Anamnez** (DB kaydı + autosave taslak kurtarma)
- Klinik Kart > **Ölçümler** (Ölçüm ekle + liste + BMI)
- Klinik Kart > Özet (son ölçüm özeti)

## Kurulum (Windows / PowerShell)
```powershell
cd .\NutriNexus_Sprint2
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m src.main
```

## Notlar
- Varsayılan veritabanı: `C:\nutrinexus_backup\nutrinexus.db`
- Log: `C:\nutrinexus_backup\logs\app.log`
- Eğer C: yazılamazsa otomatik olarak kullanıcı dizinine düşer.

## Güncelleme Paketi (ZIP) Oluşturma
GitHub kullanmadan hızlıca güncelleme paylaşmak için tek bir ZIP oluşturabilirsiniz:

```powershell
.\make_update_zip.bat
```

Komut, repo kökünde `nutrinexus_updates.zip` dosyasını üretir. Bu ZIP içinde:
- `src/main.py`
- `src/ui/screens/settings.py`
- `src/ui/theme/style.qss`
- `src/ui/theme/palette.py`
- `apply_settings_layout_update_onefile.bat`

ZIP’i başka bir bilgisayara kopyalayıp, aynı repo köküne açarak güncelleyebilirsiniz.

## Autosave (Elektrik kesintisi senaryosu)
- Anamnez alanı **10 saniyede bir** `autosave_drafts` tablosuna taslak atar.
- Uygulama yeniden açılınca aynı danışan için taslak varsa **kurtarma bildirimi** çıkar.

## Klasör Yapısı
```
src/
  main.py
  app/
    bootstrap.py
    state.py
  ui/
    main_window.py
    theme/
      palette.py
      style.qss
    screens/
      dashboard.py
      clients.py
      appointments.py
      foods.py
      templates.py
      settings.py
    dialogs/
      client_form_dialog.py
  db/
    connection.py
    schema.py
  services/
    clients_service.py
    clinical_service.py
    measurements_service.py
    autosave.py
    backup.py
    logger.py
  assets/
    nutrinexus_logo.png
```


## Sprint 3.6 – Hesaplamalar Final
- Ölçümden otomatik gelen boy/kilo (Hesaplamalar ekranı sadece gösterir)
- Hedef kcal kartları (TDEE bazlı Koruma/Kilo Ver/Kilo Al + seçili hedef)
- Tarih gösterimi TR formatında (DD.MM.YYYY)


## Sprint 3.7
- PDF Danışan Raporu (Arial, TR tarih, ölçümden boy/kilo, hesaplama özeti)


## Sprint 4.7 — Besin Tüketimi (Yarı Otomatik)
- Dünü kopyala
- Öğün şablonları
- Sık kullanılanlar + autocomplete
- Mini besin kataloğu (kcal/100g) + offline cache
- İnternetten CSV ile katalog güncelleme (opsiyonel)
