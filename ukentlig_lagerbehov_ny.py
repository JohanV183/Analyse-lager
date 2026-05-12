import streamlit as st
import pandas as pd
# import matplotlib.pyplot as plt

st.set_page_config(
    page_title="Lagerbehov",
    layout="wide"
)

st.title("Behov for lagerplass")

# Sideinnstillinger
st.sidebar.header("⚙️ Innstillinger")

KAPASITET_PALLER = st.sidebar.number_input(
    "Lagerkapasitet (palleplasser)",
    min_value=0,
    max_value=5000,
    value=400,
    step=10
)

# Filopplasting
uploaded_file = st.file_uploader(
    "Last opp ukeplan (Excel)",
    type=["xlsx", "xlsm", "xls"]
)

if uploaded_file is None:
    st.info("Last opp en ukeplan for å starte.")
    st.stop()

# Les Excel
df_raw = pd.read_excel(
    uploaded_file,
    sheet_name="Blandeplan",
    header=None
)

# Finn header-raden (der Ordrenummer finnes)
header_row = df_raw.index[
    df_raw.apply(
        lambda r: r.astype(str)
        .str.contains("Ordrenummer", case=False, na=False)
        .any(),
        axis=1
    )
][0]

df = df_raw.iloc[header_row + 1:].copy()
df.columns = df_raw.iloc[header_row]

# Rens kolonnenavn
df.columns = (
    df.columns
    .map(str)
    .str.strip()
    .str.replace("\n", "")
    .str.replace(" ", "_")
)
# Hent uke fra filnavn (fallback)
uke_fra_fil = (
    pd.Series(uploaded_file.name)
    .str.extract(r"(?i)uke\s*(\d+)")
    .iloc[0, 0]
)

if pd.isna(uke_fra_fil):
    st.error("Fant ikke uke i filnavnet.")
    st.stop()

uke_fra_fil = int(uke_fra_fil)


# Lag planuke
df["planuke"] = (
    df["Blande_uke"]
    .astype(str)
    .str.extract(r"(\d+)")
)

df.loc[df["planuke"].isna(), "planuke"] = uke_fra_fil
df["planuke"] = df["planuke"].astype(int)
assert df["planuke"].notna().all()

# Filtrer lagerførte blandinger (6-serien)
df["Blanding"] = df["Blanding"].astype(str)
df["materialkode"] = df["Blanding"].str.extract(r"(\d{6})")

df = df[df["materialkode"].str.startswith("6", na=False)]

# Palleplasser = Lots × 2
df["Lots"] = pd.to_numeric(
    df["Lots"].astype(str).str.replace(",", ".", regex=False),
    errors="coerce"
)

df["palleplasser"] = df["Lots"] * 2

# prod_unik: én rad per Ordrenummer
df = df.sort_values("planuke", ascending=False)

prod_unik = df.drop_duplicates(
    subset="Ordrenummer",
    keep="first"
).copy()

st.write(f"ℹ️ Antall ordre: {len(prod_unik)}")

# Daglig lagerbevegelse
prod_unik["Frist_blanding"] = pd.to_datetime(prod_unik["Frist_blanding"])
prod_unik["Pakke_dato"] = pd.to_datetime(prod_unik["Pakke_dato"])

# Inn på lager
inn = (
    prod_unik
    .groupby("Frist_blanding")["palleplasser"]
    .sum()
    .rename("inn")
)

# Ut av lager
ut = (
    prod_unik
    .groupby("Pakke_dato")["palleplasser"]
    .sum()
    .rename("ut")
)

lager_daglig = pd.concat([inn, ut], axis=1).fillna(0)
lager_daglig["netto"] = lager_daglig["inn"] - lager_daglig["ut"]
lager_daglig["lagerbeholdning"] = lager_daglig["netto"].cumsum()


# Avgrens til faktisk planperiode

start_dato = prod_unik["Frist_blanding"].min()
slutt_dato = prod_unik["Pakke_dato"].max()

lager_daglig_plot = lager_daglig.loc[start_dato:slutt_dato]

# Visualisering
st.subheader("📈 Daglig lagerbehov")

fig, ax = plt.subplots(figsize=(10, 4))

ax.plot(
    lager_daglig.index,
    lager_daglig["lagerbeholdning"],
    label="Lagerbeholdning"
)

ax.axhline(
    KAPASITET_PALLER,
    color="red",
    linestyle="--",
    label=f"Kapasitet ({KAPASITET_PALLER} paller)"
)

ax.set_xlabel("Dato")
ax.set_ylabel("Palleplasser")
ax.legend()

st.pyplot(fig)

# Varsel
maks_lager = lager_daglig["lagerbeholdning"].max()

if maks_lager > KAPASITET_PALLER:
    st.error(
        f"⚠️ Lagerkapasitet overskrides\n\n"
        f"Maks behov: {int(maks_lager)} paller\n"
        f"Kapasitet: {KAPASITET_PALLER} paller"
    )
else:
    st.success(
        f"✅ Lagerkapasiteten holder\n\n"
        f"Maks behov: {int(maks_lager)} paller"
    )

# Kritiske dager
kritiske_dager = lager_daglig_plot[
    lager_daglig_plot["lagerbeholdning"] > KAPASITET_PALLER
]

if not kritiske_dager.empty:
    st.subheader("🔴 Dager med kapasitetsbrudd")
    st.dataframe(
        kritiske_dager[["lagerbeholdning"]],
        use_container_width=True
    )

kritiske_dager = lager_daglig_plot[
    lager_daglig_plot["lagerbeholdning"] > KAPASITET_PALLER
]

if kritiske_dager.empty:
    st.info("✅ Ingen kritiske dager å analysere per blandingstype.")
    st.stop()
bidrag_liste = []

# Lager liste over type blandinger
for dato in kritiske_dager.index:
    bidrag = (
        prod_unik[
            (prod_unik["Frist_blanding"] <= dato)
            & (prod_unik["Pakke_dato"] > dato)
        ]
        .groupby("Materialnummer")["palleplasser"]
        .sum()
        .reset_index()
    )
    bidrag["Dato"] = dato
    bidrag_liste.append(bidrag)

kritiske_per_materiale = pd.concat(bidrag_liste, ignore_index=True)

kritiske_per_materiale = kritiske_per_materiale.merge(
    prod_unik[
        ["Materialnummer", "Blanding"]
    ].drop_duplicates(),
    on="Materialnummer",
    how="left"
)


# Visualiserer blandinger 
st.subheader("🔍 Kritiske dager – fordelt på material")

st.dataframe(
    kritiske_per_materiale
    .sort_values(["Dato", "palleplasser"], ascending=[True, False]),
    use_container_width=True
)

# Oppsummering
oppsummering_type = (
    kritiske_per_materiale
    .groupby("Materialnummer")["palleplasser"]
    .sum()
    .sort_values(ascending=False)
)

st.subheader("📊 Hvem driver kapasitetsbruddene?")

st.bar_chart(oppsummering_type)

