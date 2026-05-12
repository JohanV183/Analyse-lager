import streamlit as st
import pandas as pd


# Kapasitet per lagerseksjon
# (1 Storage Bin = 1 pallplass)
SEKSJON_KAPASITET = {
    "420": 476,
    "403": 165,
    "409": 120,
    "410": 150,
}

st.set_page_config(
    page_title="Lageranalyse",
    layout="wide"
)

st.title("Lageranalyse")

# Fanevisning
tab_lager, tab_liggetid, tab_sperret, tab_dato = st.tabs([
    "Lagerstatus",
    "Bevegelse",
    "Sperret lager",
    "Dato-status"
])

# FUNKSJONER
# Normaliserer ID-kolonner
def normaliser_id_kolonne(serie: pd.Series) -> pd.Series:
    return (
        pd.to_numeric(
            serie.replace("<<empty>>", None),
            errors="coerce"
        )
        .astype("Int64")          # fjerner desimaler korrekt
        .astype(str)              # gjør til tekst-ID
        .replace("<NA>", None)    # rydd NaN
    )

# Setter fargeskalering på S/Q
def fargekode_stock_category_med_alder(rad):
    i_dag = pd.Timestamp.today().normalize()

    sled = rad.get("SLED/BBD")
    kategori = rad.get("Stock Category")

    if pd.isna(sled):
        return [""] * len(rad)

    dager_til_sled = (sled - i_dag).days

    # Q = rødskala
    if kategori == "Q":
        if dager_til_sled < 7:
            farge = "#cc0000"   # kritisk rød
        elif dager_til_sled < 30:
            farge = "#ff4d4d"
        elif dager_til_sled < 60:
            farge = "#ff9999"
        else:
            farge = "#ffe5e5"

    # S = gulskala
    elif kategori == "S":
        if dager_til_sled < 7:
            farge = "#e6b800"   # kritisk gul
        elif dager_til_sled < 30:
            farge = "#ffcc00"
        elif dager_til_sled < 60:
            farge = "#ffe066"
        else:
            farge = "#fff3cd"

    else:
        return [""] * len(rad)

    return [f"background-color: {farge}"] * len(rad)

def fargekode_stille_materialer(rad):
    dager = rad.get("Dager_siden")

    if pd.isna(dager):
        return [""] * len(rad)

    if dager >= 100:
        farge = "#f8d7da"   # mørk rød
    elif dager >= 30:
        farge = "#fff3cd"   # oransje/gul
    elif dager >= 14:
        farge = "#fff9db"   # lys gul
    else:
        return [""] * len(rad)

    return [f"background-color: {farge}"] * len(rad)

def fargekode_utlop(rad):
    dager = rad.get("Dager_til_utlop")

    if pd.isna(dager):
        return [""] * len(rad)

    if dager < 0:
        farge = "#f8d7da"   # utløpt
    elif dager <= 30:
        farge = "#fff3cd"   # kritisk nær
    else:
        farge = "#d4edda"   # OK/trygg (>= 31 dager)

    return [f"background-color: {farge}"] * len(rad)



# Filinnlasting
st.markdown("")
with st.expander("Last opp Excel-fil", expanded=True):
    uploaded_file = st.file_uploader(
        "Velg Excel-fil",
        type=["xlsx", "xls"]
    )


if not uploaded_file:
    st.info("Last opp en Excel-fil for å starte analysen.")
    st.stop()


# Les fil, lager kolonneliste eksplisitt
df = pd.read_excel(uploaded_file, header=None)

df.columns = [
    "Storage Type",
    "Storage Section",
    "Storage Bin",
    "Material",
    "Storage Unit Type",
    "Storage Unit",
    "Stock Category",
    "Total Stock",
    "Available stock",
    "Stock for putaway",
    "Pick quantity",
    "Batch",
    "SLED/BBD",
    "GR Date",
    "Special Stock",
    "Last movement",
]

df = df.iloc[1:].reset_index(drop=True)
df.columns = df.columns.map(str).str.strip()



# Normaliser ID-kolonner 
for col in ["Material", "Batch", "Storage Unit"]:
    if col in df.columns:
        df[col] = normaliser_id_kolonne(df[col])
        
# Normaliser Storage Section som ID (uten .0)
df["Storage Section"] = (
    pd.to_numeric(df["Storage Section"], errors="coerce")
    .astype("Int64")
    .astype(str)
    .replace("<NA>", None)
)

# Normaliserer dato-kolonner
for col in ["SLED/BBD", "GR Date", "Last movement"]:
    if col in df.columns:
        df[col] = pd.to_datetime(
            df[col],
            errors="coerce",
            dayfirst=True
        )
        

# Finn lagerseksjon
seksjon_col = None
for col in df.columns:
    if "storage section" in col.lower() or "lagerseksjon" in col.lower():
        seksjon_col = col
        break

if seksjon_col is None:
    st.error("Fant ingen lagerseksjon-kolonne automatisk.")
    st.stop()

# Rens lagerseksjon-verdier
df["_lagerseksjon_renset"] = (
    pd.to_numeric(df[seksjon_col], errors="coerce")
    .astype("Int64")        # fjerner .0 korrekt
    .astype(str)            # gjør klar for UI
)

prioritet = {"420": 0, "403": 1, "409": 2, "410": 3}

tilgjengelige_seksjoner = sorted(
        (s for s in df["_lagerseksjon_renset"].dropna().unique()
        if s in SEKSJON_KAPASITET),
        key=lambda s: prioritet.get(s, 99)
)

valgt_seksjon = st.selectbox("Velg lagerseksjon", tilgjengelige_seksjoner)
KAPASITET = SEKSJON_KAPASITET[valgt_seksjon]

df_seksjon = df[df["_lagerseksjon_renset"] == valgt_seksjon].copy()


# Finn Storage Bin automatisk
bin_col = None
for col in df.columns:
    if col.lower().strip() in [ 
        "storage bin", "storage_bin", "storagebin", "bin", "lagerplass", "plass"
    ]:
        bin_col = col
        break

if bin_col is None:
    st.error("Fant ingen Storage Bin-kolonne automatisk.\n\n")
    st.stop()

df_seksjon["Storage Bin"] = df_seksjon[bin_col].astype(str)


# Rens Material: kun rene tall er gyldig material
df_seksjon["Material_visning"] = df_seksjon["Material"]

df_seksjon["_har_gyldig_material"] = (
    df_seksjon["Material"].str.fullmatch(r"\d+").notna()
)

# Fyllgrad
bin_status = (
    df_seksjon
    .groupby("Storage Bin")["_har_gyldig_material"]
    .any()   
)

opptatte_bins = bin_status[bin_status].index.tolist()
tomme_bins = bin_status[~bin_status].index

brukte_bins = len(opptatte_bins)
ledig_kapasitet = KAPASITET - brukte_bins
fyllgrad = brukte_bins / KAPASITET * 100

with st.expander("Status", expanded=False):

    st.success(f"Fil lastet inn med {len(df)} rader")

    st.write("Antall rader i valgt seksjon:", len(df_seksjon))
    st.write("Bins med gyldig materialkode:", len(opptatte_bins))
    st.write("Bins uten gyldig materialkode:", len(tomme_bins))


# Hva beslaglegger flest plasser?
# Gruppér på material og tell unike Storage Bins
top_material = (
    df_seksjon[df_seksjon["_har_gyldig_material"]]
    .groupby("Material_visning")["Storage Bin"]
    .nunique()
    .sort_values(ascending=False)
    .head(10)
)


# Lagerstatus
with tab_lager:
    st.subheader(f"Lagerstatus – Seksjon {valgt_seksjon}")

    col4, col1, col2, col3 = st.columns(4)
    col4.metric("Total kapasitet (Bins)", KAPASITET)
    col1.metric("Opptatte Bins", brukte_bins)
    col2.metric("Ledige Bins", ledig_kapasitet)
    col3.metric("Fyllgrad", f"{fyllgrad:.1f} %")

    if fyllgrad >= 100:
        st.error("Lagerseksjonen er full!")
    elif fyllgrad > 85:
        st.warning("⚠️ Lageret nærmer seg fullt!")
    else:
        st.success("✅ Kapasitet OK")

    # Top 10 materialer
    st.subheader("Top 10 materialer – antall plasser")

    # Sikkerhet: Hvis ingen gyldige materialer finnes
    if top_material.empty:
        st.info("Ingen gyldige materialkoder funnet.")
    else:
        st.bar_chart(top_material)



# Stillestående varer
i_dag = pd.Timestamp.today().normalize()

df_stille = df[
    (df["Last movement"].notna()) &
    (df["Material"].str.fullmatch(r"\d+").notna()) &
    (df["Storage Section"] == valgt_seksjon)
].copy()

# Dager siden siste bevegelse
df_stille["Dager_siden_bevegelse"] = (
    i_dag - df_stille["Last movement"]
).dt.days

# Aggreger per material
stille_materialer = (
    df_stille
    .groupby("Material")
    .agg(
        Sist_beveget=("Last movement", "min"),
        Dager_siden=("Dager_siden_bevegelse", "max"),
        Pallplasser=("Storage Bin", "nunique"),
        Stock_Category=("Stock Category", lambda x: ", ".join(sorted(x.dropna().unique()))),
        Lagerseksjoner=("Storage Section", lambda x: ", ".join(sorted(x.unique()))),
    )
    .sort_values("Dager_siden", ascending=False)
    .reset_index()
)

# Prioriter valgt lagerseksjon i sorteringen
stille_materialer_sortert = (
    stille_materialer
    .assign(
        _prioritet=lambda df_: df_["Lagerseksjoner"]
            .str.contains(fr"\b{valgt_seksjon}\b", regex=True)
            .map({True: 0, False: 1})
    )
    .sort_values(
        by=["_prioritet", "Dager_siden"],
        ascending=[True, False]
    )
    .drop(columns="_prioritet")
)

# KPI-terskel avhengig av valgt lagerseksjon
if valgt_seksjon == "420":
    stale_grense = 14
else:
    stale_grense = 90

antall_stille = (stille_materialer["Dager_siden"] > stale_grense).sum()
pallplasser_stille = stille_materialer.loc[
    stille_materialer["Dager_siden"] > stale_grense,
    "Pallplasser"
].sum()


# Etter valg av lagertype
df_base = df.copy()

# Terskelverdier for sist bevegelse
TERS_BEVG = {
    "420": 14,
    "403": 60,
}
DEFAULT_TERSKEL = 60

# Søylediagram over siste bevegelser
i_dag = pd.Timestamp.today().normalize()

df_lang = df_base[
    df_base["Last movement"].notna()
].copy()

df_lang["Dager_siden_bevegelse"] = (
    i_dag - df_lang["Last movement"]
).dt.days

def er_over_terskel(rad):
    seksjon = rad["Storage Section"]
    terskel = TERS_BEVG.get(seksjon, DEFAULT_TERSKEL)
    return rad["Dager_siden_bevegelse"] > terskel

df_lang["Over_terskel"] = df_lang.apply(er_over_terskel, axis=1)

pallplasser_per_seksjon = (
    df_lang[df_lang["Over_terskel"]]
    .groupby("Storage Section")["Storage Bin"]
    .nunique()
    .sort_index()
)

with tab_liggetid:
    st.subheader(f"Stillestående varer - Seksjon {valgt_seksjon}")

    c1, c2 = st.columns(2)
    c1.metric(
        f"Materialer uten bevegelse > {stale_grense} dager",
        antall_stille
    )
    c2.metric(
        f"Pallplasser > {stale_grense} dager",
        pallplasser_stille
    )

    st.dataframe(
        stille_materialer_sortert
            .head(20)
            .style
            .apply(fargekode_stille_materialer, axis=1)
            .format({
                "Sist_beveget": lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) else "",
                "Dager_siden": "{:.0f}",
            })
            .set_properties(subset=["Dager_siden"], **{"text-align": "right"})
            .set_properties(subset=["Material"], **{"font-weight": "bold"}),
        use_container_width=True
    )

    st.divider()

    # Sammenlikning mellom seksjoner
    st.markdown("### Sammenlikning mellom lagerseksjoner")

    st.text(
        "Viser antall pallplasser per lagerseksjon som ligger over angitt terkselnivå\n")

    st.caption(
        "Terskler: "
        "Seksjon 420 > 14 dager + "
        f"Øvrige seksjoner > {DEFAULT_TERSKEL} dager"
    )
    st.caption("Seksjon 420 har lavere terskel som følge av at andre seksjoner også har råvare og ikke kun blandinger")

    if pallplasser_per_seksjon.empty:
        st.info("Ingen pallplasser overstiger tersklene.")
    else:
        st.bar_chart(pallplasser_per_seksjon)


# Sortere på Q og S
def hent_s_q_lagerlinjer(df, dato_kolonne):
    df = df.copy()
    df[dato_kolonne] = pd.to_datetime(df[dato_kolonne], errors="coerce")
    return df[df["Stock Category"].isin(["S", "Q"])]

df_sq = hent_s_q_lagerlinjer(df, "GR Date")

df_sq["Material_visning"] = df_sq["Material"]
df_sq["_har_gyldig_material"] = (
    df_sq["Material"].str.fullmatch(r"\d+").notna()
)

material_telling = (
    df_sq[df_sq["_har_gyldig_material"]]
    .groupby("Stock Category")["Material_visning"]
    .nunique()
)

pallplasser_telling = (
    df_sq[df_sq["_har_gyldig_material"]]
    [["Storage Bin", "Stock Category"]]
    .drop_duplicates()
    .groupby("Stock Category")["Storage Bin"]
    .count()
)

antall_s = material_telling.get("S", 0)
antall_q = material_telling.get("Q", 0)

pallplasser_s = pallplasser_telling.get("S", 0)
pallplasser_q = pallplasser_telling.get("Q", 0)


df_sq_sortert = df_sq.sort_values(
    by=["SLED/BBD", "Stock Category"],
    na_position="last"
)

df_visning = df_sq_sortert.drop(
    columns=[
        "Storage Type",
        "Stock for putaway",
        "Pick quantity",
        "Special Stock",
        "_lagerseksjon_renset",
        "_har_gyldig_material",
        "Material_visning",
    ],
    errors="ignore"
)

with tab_sperret:

    with st.container(border=True):
        st.subheader("Sperret lager")

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Materialer i S", antall_s)
            st.metric("Pallplasser i S", pallplasser_s)

        with c2:
            st.metric("Materialer i Q", antall_q)
            st.metric("Pallplasser i Q", pallplasser_q)

    st.dataframe(
        df_visning
            .style
            .apply(fargekode_stock_category_med_alder, axis=1)
            .format({
                "Total Stock": lambda x: f"{int(x)}" if pd.notna(x) and str(x).replace('.', '', 1).isdigit() else x,
                "Available stock": lambda x: f"{int(x)}" if pd.notna(x) and str(x).replace('.', '', 1).isdigit() else x,
                "Storage Section": lambda x: f"{int(x)}" if pd.notna(x) and str(x).isdigit() else x,
                "Storage Unit": lambda x: f"{int(x)}" if pd.notna(x) and str(x).isdigit() else x,
                "Batch": lambda x: f"{int(x)}" if pd.notna(x) and str(x).isdigit() else x,
                "SLED/BBD": lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) else "",
                "GR Date": lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) else "",
                "Last movement": lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) else "",
            }),
            use_container_width=True
    )
    
    st.markdown(
        """
    Fargene i tabellen viser **hvor kritisk en lagerlinje er basert på utløpsdato (SLED/BBD)**:

    **Stock Category Q**  
    - 🟥 **Mørk rød**: Utløpt eller < 7 dager til SLED 
    - 🟥 **Rød**: 7–30 dager til SLED  
    - 🟥 **Lys rød**: > 30 dager til SLED  

    **Stock Category S**  
    - 🟨 **Mørk gul**: Utløpt eller < 7 dager til SLED   
    - 🟨 **Gul**: 7–30 dager til SLED  
    - 🟨 **Lys gul**: > 30 dager til SLED  

    **Mørkere farge = høyere risiko og høyere prioritet for oppfølging**
    """
    
    )
    st.divider()
    st.markdown("")


# Dato-varer
df_utlop = df[
    df["SLED/BBD"].notna() &
    df["Material"].str.fullmatch(r"\d+").notna()
].copy()

df_utlop["Dager_til_utlop"] = (
    df_utlop["SLED/BBD"] - i_dag
).dt.days

# Aggreger per material
utlopende_materialer = (
    df_utlop
    .groupby("Material")
    .agg(
        Tidligste_SLED=("SLED/BBD", "min"),
        Dager_til_utlop=("Dager_til_utlop", "min"),
        Pallplasser=("Storage Bin", "nunique"),
        Stock_Category=("Stock Category", lambda x: ", ".join(sorted(x.dropna().unique()))),
        Lagerseksjoner=("Storage Section", lambda x: ", ".join(sorted(x.unique()))),
    )
    .sort_values("Dager_til_utlop")
    .reset_index()
)

kritisk_grense = 0  # dager til utløpsdato

antall_kritisk = (utlopende_materialer["Dager_til_utlop"] < kritisk_grense).sum()
pallplasser_kritisk = utlopende_materialer.loc[
    utlopende_materialer["Dager_til_utlop"] < kritisk_grense,
    "Pallplasser"
].sum()



with tab_dato:

    st.subheader("Datohåndtering")

    c1, c2 = st.columns(2)
    c1.metric("Materialer som har gått ut på dato", antall_kritisk)
    c2.metric("Antall pallplasser", pallplasser_kritisk)

    st.markdown("")
    
    st.subheader("Oversikt")
    st.text("De første 20 varene som har gått ut eller nærmer seg utløpsdato")
    st.dataframe(
        utlopende_materialer
            .head(20)
            .style
            .apply(fargekode_utlop, axis=1)
            .format({
                "Tidligste_SLED": lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) else "",
                "Dager_til_utlop": "{:.0f}",
            })
            .set_properties(subset=["Dager_til_utlop"], **{"text-align": "right"})
            .set_properties(subset=["Material"], **{"font-weight": "bold"}),
        use_container_width=True
        
    )
    st.markdown("Beskrivelse: ")
    st.markdown("- Rød = kritisk, over utløpsdato \n"
                "- Oransj = varsel, mindre enn 31 dager til utløpsdato \n"
                "- Grønn = OK, lengre enn 30 dager til utløpsdato")


# Rådata 
with st.expander("Vis rådata for valgt seksjon"):
    st.dataframe(df_seksjon, use_container_width=True)

# Opptatte bins
with st.expander("Opptatte bins"):
    st.dataframe(
        df_seksjon[
            df_seksjon["_har_gyldig_material"]
        ][["Storage Bin", "Material_visning"]]
        .drop_duplicates(),
        use_container_width=True
    )