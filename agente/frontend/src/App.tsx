import { useCallback, useEffect, useState } from "react";

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

const usd = (x: number) => x.toLocaleString("en-US", { maximumFractionDigits: 2 });

async function llamar(ruta: string, metodo = "GET") {
  const r = await fetch(`/api${ruta}`, { method: metodo });
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`${r.status} ${cuerpo.detail ?? r.statusText}`);
  return cuerpo;
}

export default function App() {
  const [e, setE] = useState<Estado | null>(null);
  const [p, setP] = useState<Pron | null>(null);
  const [falla, setFalla] = useState("");

  const cargar = useCallback(
    () => {
      llamar("/pronostico").then(setP, () => setP(null));   // si MEXC falla, /estado sigue mostrando el resto
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
  const c = { textAlign: "left", paddingRight: 12 } as const;
  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 900, margin: "1rem auto", padding: "0 1rem" }}>
      <h1>Agente de IA · {e?.simbolo ?? "…"} (Paper)</h1>
      {falla && <p role="alert" style={{ color: "#b00020" }}>Error: {falla}</p>}
      {e && <>
        <p>Estado: <b>{e.estado}</b>{" "}
          <button onClick={accion("/iniciar")}>Iniciar</button>{" "}
          <button onClick={accion("/pausar")}>Pausar</button>{" "}
          <button onClick={accion("/detener", "Detener bloquea toda orden nueva. ¿Seguro?")}>Detener</button>{" "}
          <button onClick={accion("/liquidar", "Vender toda la posición al último cierre. ¿Seguro?")}>Liquidar</button></p>

        <h2>Cartera</h2>
        <p>Efectivo {usd(e.efectivo)} USDT · posición {e.unidades} BTC · patrimonio {v ? usd(v.patrimonio) : "—"} USDT
          (capital inicial {usd(e.capital_inicial)}, costo {e.costo}) · límites: exposición {e.limites.exposicion_max}, pérdida diaria {e.limites.perdida_diaria_max}</p>

        <h2>Pronóstico e indicadores</h2>
        {p ? <p>Vela de datos {p.vela} (cierre {usd(p.cierre_base)}) · modelo {p.modelo} · rendimiento estimado <b>{(100 * p.rendimiento_estimado).toFixed(3)} %</b><br />
          dist_sma20 {(100 * p.variables.dist_sma20).toFixed(2)} % · vol20 {(100 * p.variables.vol20).toFixed(2)} % · r_lag0 {(100 * p.variables.r_lag0).toFixed(2)} %</p>
          : <p>Sin pronóstico (datos de MEXC no válidos o sin respuesta).</p>}

        <h2>Última decisión</h2>
        {d ? <p>Vela {d.fecha}: <b>{d.accion}</b> (riesgo: {e.estado === "detenido" ? "bloqueado" : "dentro de límites"}) · estimado {(100 * d.rendimiento_estimado).toFixed(3)} %<br />{d.motivo}</p> : <p>Sin decisiones todavía.</p>}

        <h2>Órdenes (últimas 20)</h2>
        <table><thead><tr>{["Fecha", "Lado", "Cantidad", "Precio", "Estado", "Motivo"].map((h) => <th key={h} style={c}>{h}</th>)}</tr></thead>
          <tbody>{e.ordenes.map((o) => <tr key={o.id}><td style={c}>{o.fecha}</td><td style={c}>{o.lado}</td><td style={c}>{o.cantidad}</td><td style={c}>{usd(o.precio)}</td><td style={c}>{o.estado}</td><td style={c}>{o.motivo}</td></tr>)}</tbody></table>

        <h2>Errores (últimos 20)</h2>
        {e.errores.length === 0 ? <p>Ninguno.</p> :
          <ul>{e.errores.map((r) => <li key={r.id}>{r.momento} · <b>{r.etapa}</b>: {r.detalle}</li>)}</ul>}
      </>}
    </main>
  );
}
