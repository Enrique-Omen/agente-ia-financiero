import { useCallback, useEffect, useState } from "react";
import Grafica from "./Grafica";
import "./estilos.css";

type Orden = { id: number; fecha: string; lado: string; cantidad: number; precio: number; estado: string; motivo: string };
type Fallo = { id: number; momento: string; etapa: string; detalle: string };
type Estado = {
  estado: string; simbolo: string; efectivo: number; unidades: number;
  ultima_vela: { fecha: string; patrimonio: number } | null;
  ultima_decision: { fecha: string; accion: string; motivo: string; rendimiento_estimado: number } | null;
  ordenes: Orden[]; errores: Fallo[];
  limites: { exposicion_max: number; perdida_diaria_max: number };
  capital_inicial: number; costo: number;
};

type Pron = { vela: string; cierre_base: number; rendimiento_estimado: number; variables: Record<string, number>; modelo: string };

type Hist = { velas: { fecha: string; precio: number; patrimonio: number }[]; ordenes: { fecha: string; lado: string; precio: number }[]; capital_inicial: number };

const usd = (x: number) => x.toLocaleString("en-US", { maximumFractionDigits: 2 });

async function llamar(ruta: string, metodo = "GET") {
  const r = await fetch(`/api${ruta}`, { method: metodo });
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`${r.status} ${cuerpo.detail ?? r.statusText}`);
  return cuerpo;
}

const pct = (x: number, d = 2) => `${x >= 0 ? "+" : ""}${(100 * x).toFixed(d)} %`;
const corto = (x: number) => (Math.abs(x) >= 1000 ? `${(x / 1000).toFixed(1)}k` : x.toFixed(0));
// El motivo del LLM viene como "LLM modelo · Ollama … · 6655 ms: justificación"; se separa la ficha técnica de la justificación.
const partir = (m: string) => { const i = m.indexOf(" ms: "); return i < 0 ? { ficha: "", texto: m } : { ficha: m.slice(0, i + 3), texto: m.slice(i + 5) }; };

const CLAVES: [string, string][] = [
  ["dist_sma20", "Distancia del cierre a su media móvil de 20 días."],
  ["vol20", "Volatilidad: desviación de los rendimientos de 20 días."],
  ["r_lag0", "Rendimiento del último día."],
  ["r_lag1", "Rendimiento de hace dos días."],
];

export default function App() {
  const [e, setE] = useState<Estado | null>(null);
  const [p, setP] = useState<Pron | null>(null);
  const [h, setH] = useState<Hist | null>(null);
  const [falla, setFalla] = useState("");
  const [tema, setTema] = useState(() => localStorage.getItem("tema") ?? (matchMedia("(prefers-color-scheme: light)").matches ? "claro" : "oscuro"));
  useEffect(() => { document.documentElement.dataset.tema = tema; localStorage.setItem("tema", tema); }, [tema]);

  const cargar = useCallback(
    () => {
      llamar("/pronostico").then(setP, () => setP(null));   // si MEXC falla, /estado sigue mostrando el resto
      llamar("/historial").then(setH, () => setH(null));
      return llamar("/estado").then((x) => { setE(x); setFalla(""); }, (x) => setFalla((x as Error).message));
    },
    [],
  );
  useEffect(() => { cargar(); const t = setInterval(cargar, 10000); return () => clearInterval(t); }, [cargar]);

  const accion = (ruta: string, aviso?: string) => async () => {
    if (aviso && !confirm(aviso)) return;
    try { await llamar(ruta, "POST"); setFalla(""); } catch (x) { setFalla((x as Error).message); }
    cargar();
  };

  const d = e?.ultima_decision, v = e?.ultima_vela;
  const velas = h?.velas ?? [];
  const fechas = velas.map((x) => x.fecha);
  const capital = e?.capital_inicial ?? 0;
  const rend = v && capital ? v.patrimonio / capital - 1 : null;
  const hold = velas.length ? velas.map((x) => (capital * x.precio) / velas[0].precio) : [];
  const rendHold = hold.length ? hold[hold.length - 1] / capital - 1 : null;
  const marcas = (h?.ordenes ?? []).map((o) => ({ i: fechas.indexOf(o.fecha), lado: o.lado })).filter((m) => m.i >= 0);
  const dec = d ? partir(d.motivo) : null;
  const bloqueado = e?.estado === "detenido";

  return (
    <div className="app">
      <header>
        <div>
          <span className="ojo">{e?.simbolo ?? "BTCUSDT"} · simulación en papel{import.meta.env.VITE_DEMO && <em className="demo">demo: replay de 20 velas</em>}</span>
          <h1>Agente de IA financiero</h1>
        </div>
        <div className="barra">
          <button className="ghost" onClick={() => setTema(tema === "oscuro" ? "claro" : "oscuro")} aria-label="Cambiar tema">{tema === "oscuro" ? "Claro" : "Oscuro"}</button>
          <button onClick={accion("/iniciar")}>Iniciar</button>
          <button onClick={accion("/pausar")}>Pausar</button>
          <button className="aviso" onClick={accion("/detener", "Detener bloquea toda orden nueva. ¿Seguro?")}>Detener</button>
          <button className="aviso" onClick={accion("/liquidar", "Vender toda la posición al último cierre. ¿Seguro?")}>Liquidar</button>
        </div>
      </header>
      {falla && <p role="alert" className="alerta">Error: {falla}</p>}
      {!e && !falla && <p className="vacio">Cargando…</p>}
      {e && <main>
        <section className="kpis">
          <article className="tarjeta">
            <span className="ojo">Estado</span>
            <b className={`estado ${e.estado}`}><i />{e.estado}</b>
            <small>Costo por operación {e.costo}</small>
          </article>
          <article className="tarjeta">
            <span className="ojo">Patrimonio</span>
            <b className="num">{v ? usd(v.patrimonio) : "—"}<u>USDT</u></b>
            <small>Capital inicial {usd(e.capital_inicial)}{rend !== null && <> · <span className={rend >= 0 ? "sube" : "baja"}>{pct(rend)}</span></>}</small>
          </article>
          <article className="tarjeta">
            <span className="ojo">Cartera</span>
            <b className="num">{usd(e.efectivo)}<u>USDT</u></b>
            <small>Posición {e.unidades} BTC · exp. máx. {pct(e.limites.exposicion_max, 0).replace("+", "")}</small>
          </article>
          <article className="tarjeta">
            <span className="ojo">Pronóstico</span>
            {p ? <><b className={`num ${p.rendimiento_estimado >= 0 ? "sube" : "baja"}`}>{pct(p.rendimiento_estimado, 3)}</b>
              <small>Vela {p.vela} (MEXC en vivo) · {p.modelo}</small></>
              : <><b className="num">—</b><small>Sin datos válidos de MEXC</small></>}
          </article>
        </section>

        <section className="graficas">
          <article className="tarjeta">
            <div className="cab"><h2>Patrimonio del agente vs comprar y mantener</h2>
              {rend !== null && rendHold !== null && <span className="resumen">Agente <b className={rend >= 0 ? "sube" : "baja"}>{pct(rend)}</b> · B&amp;H <b className={rendHold >= 0 ? "sube" : "baja"}>{pct(rendHold)}</b></span>}</div>
            <Grafica fechas={fechas} formato={corto}
              series={[{ nombre: "Agente", color: "var(--acento)", valores: velas.map((x) => x.patrimonio), area: true },
                       { nombre: "Comprar y mantener", color: "var(--tenue)", valores: hold, trazo: "5 4" }]} />
          </article>
          <article className="tarjeta">
            <div className="cab"><h2>Precio {e.simbolo} y operaciones</h2><span className="resumen">cierre diario</span></div>
            <Grafica fechas={fechas} formato={corto} marcas={marcas}
              series={[{ nombre: "Precio de cierre", color: "var(--texto2)", valores: velas.map((x) => x.precio) }]} />
          </article>
        </section>

        <section className="dos">
          <div className="col">
            <article className="tarjeta decision">
              <div className="cab"><h2>Última decisión del LLM</h2>{d && <span className="resumen mono">vela procesada {d.fecha}</span>}</div>
              {d && dec ? <>
                <div className="fila">
                  <span className={`etiqueta ${d.accion}`}>{d.accion}</span>
                  <span className="resumen mono">estimado {pct(d.rendimiento_estimado, 3)}</span>
                </div>
                <p className="justif">{dec.texto}</p>
                {dec.ficha && <small className="ficha">{dec.ficha}</small>}
              </> : <p className="vacio">Sin decisiones todavía.</p>}
            </article>
            <article className="tarjeta">
              <div className="cab"><h2>Riesgo y límites</h2></div>
              <span className={`veredicto ${bloqueado ? "no" : "ok"}`}>Veredicto: {bloqueado ? "bloqueado" : "dentro de límites"}</span>
              <dl className="indic dos-col">
                <div><dt>Exposición máxima</dt><dd>{pct(e.limites.exposicion_max, 0).replace("+", "")}</dd></div>
                <div><dt>Pérdida diaria máxima</dt><dd>{pct(e.limites.perdida_diaria_max, 0).replace("+", "")}</dd></div>
              </dl>
            </article>
          </div>
          <article className="tarjeta">
            <div className="cab"><h2>Indicadores</h2>{p && <span className="resumen mono">datos al {p.vela}</span>}</div>
            {p ? <>
              <dl className="claves">
                {CLAVES.map(([k, ayuda]) => <div key={k}><dt className="mono">{k}</dt><dd className="mono">{(100 * p.variables[k]).toFixed(2)} %</dd><span>{ayuda}</span></div>)}
              </dl>
              <details><summary>Ver los 20 rezagos</summary>
                <dl className="indic">
                  {Object.entries(p.variables).filter(([k]) => k.startsWith("r_lag")).map(([k, x]) => <div key={k}><dt>{k}</dt><dd>{(100 * x).toFixed(2)} %</dd></div>)}
                </dl></details>
            </> : <p className="vacio">Sin pronóstico (datos de MEXC no válidos o sin respuesta).</p>}
          </article>
        </section>

        <section className="tarjeta">
          <div className="cab"><h2>Órdenes</h2><span className="resumen">últimas 20</span></div>
          {e.ordenes.length === 0 ? <p className="vacio">Sin órdenes.</p> :
            <div className="tabla"><table>
              <thead><tr><th>Fecha</th><th>Lado</th><th className="d">Cantidad</th><th className="d">Precio</th><th>Estado</th><th>Motivo</th></tr></thead>
              <tbody>{e.ordenes.map((o) => <tr key={o.id}>
                <td className="mono">{o.fecha}</td><td><span className={`etiqueta ${o.lado}`}>{o.lado}</span></td>
                <td className="mono d">{o.cantidad}</td><td className="mono d">{usd(o.precio)}</td>
                <td>{o.estado}</td><td className="mot">{o.motivo}</td></tr>)}</tbody></table></div>}
        </section>

        <section className="tarjeta">
          <div className="cab"><h2>Errores</h2><span className="resumen">últimos 20</span></div>
          {e.errores.length === 0 ? <p className="vacio">Ninguno.</p> :
            <ul className="errores">{e.errores.map((r) => <li key={r.id}><span className="mono">{r.momento}</span> <b>{r.etapa}</b> {r.detalle}</li>)}</ul>}
        </section>
      </main>}
    </div>
  );
}
