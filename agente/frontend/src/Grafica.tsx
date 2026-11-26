import { useEffect, useRef, useState } from "react";

export type Serie = { nombre: string; color: string; valores: number[]; trazo?: string; area?: boolean };
export type Marca = { i: number; lado: string };

// Gráfica de líneas en SVG propio (sin librería): ejes, rejilla fina, cruz con valores al pasar el puntero y marcas de compra/venta.
export default function Grafica({ fechas, series, marcas = [], formato, alto = 260 }: {
  fechas: string[]; series: Serie[]; marcas?: Marca[]; formato: (x: number) => string; alto?: number;
}) {
  const caja = useRef<HTMLDivElement>(null);
  const [ancho, setAncho] = useState(640);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const ro = new ResizeObserver(([x]) => setAncho(Math.max(240, Math.round(x.contentRect.width))));
    ro.observe(caja.current!);
    return () => ro.disconnect();
  }, []);

  const n = fechas.length;
  const M = { t: 12, r: 12, b: 26, l: ancho < 480 ? 52 : 64 };
  const todos = series.flatMap((s) => s.valores);
  let lo = Math.min(...todos), hi = Math.max(...todos);
  const pad = (hi - lo || hi * 0.01 || 1) * 0.12;
  lo -= pad; hi += pad;
  const X = (i: number) => M.l + (n < 2 ? 0 : (i / (n - 1)) * (ancho - M.l - M.r));
  const Y = (v: number) => M.t + (1 - (v - lo) / (hi - lo)) * (alto - M.t - M.b);
  const ruta = (v: number[]) => v.map((y, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(y).toFixed(1)}`).join("");
  const yTicks = [0, 1, 2, 3].map((k) => lo + ((hi - lo) * k) / 3);
  const paso = Math.max(1, Math.ceil(n / (ancho < 480 ? 3 : 6)));
  const corta = (f: string) => f.slice(5);

  const mover = (ev: React.PointerEvent<SVGSVGElement>) => {
    const r = ev.currentTarget.getBoundingClientRect();
    const f = (ev.clientX - r.left - M.l) / (ancho - M.l - M.r);
    setHover(Math.min(n - 1, Math.max(0, Math.round(f * (n - 1)))));
  };

  if (n === 0) return <div className="vacio">Sin velas procesadas todavía.</div>;
  return (
    <div ref={caja} className="grafica">
      <svg width={ancho} height={alto} role="img" onPointerMove={mover} onPointerLeave={() => setHover(null)}
        aria-label={series.map((s) => s.nombre).join(" y ")}>
        {yTicks.map((t) => <g key={t}>
          <line x1={M.l} x2={ancho - M.r} y1={Y(t)} y2={Y(t)} className="rej" />
          <text x={M.l - 8} y={Y(t) + 4} textAnchor="end" className="eje">{formato(t)}</text>
        </g>)}
        {fechas.map((f, i) => i % paso === 0 && <text key={f} x={X(i)} y={alto - 6} textAnchor="middle" className="eje">{corta(f)}</text>)}
        {series.map((s) => <g key={s.nombre}>
          {s.area && <path d={`${ruta(s.valores)}L${X(n - 1)},${Y(lo)}L${X(0)},${Y(lo)}Z`} fill={s.color} opacity={0.08} />}
          <path d={ruta(s.valores)} fill="none" stroke={s.color} strokeWidth={s.trazo ? 1.5 : 2} strokeDasharray={s.trazo} strokeLinejoin="round" />
        </g>)}
        {marcas.map((m, k) => {
          const y = Y(series[0].valores[m.i]), compra = m.lado === "compra", x = X(m.i);
          return <path key={k} className={compra ? "m-compra" : "m-venta"}
            d={compra ? `M${x},${y - 3}l6,-11h-12z` : `M${x},${y + 3}l6,11h-12z`}>
            <title>{`${compra ? "Compra" : "Venta"} · ${fechas[m.i]}`}</title></path>;
        })}
        {hover !== null && <g>
          <line x1={X(hover)} x2={X(hover)} y1={M.t} y2={alto - M.b} className="cruz" />
          {series.map((s) => <circle key={s.nombre} cx={X(hover)} cy={Y(s.valores[hover])} r={3.5} fill={s.color} className="punto" />)}
        </g>}
      </svg>
      {hover !== null && <div className="tip" style={{ left: Math.min(Math.max(X(hover), 90), ancho - 90) }}>
        <b>{fechas[hover]}</b>
        {series.map((s) => <span key={s.nombre}><i style={{ background: s.color }} />{s.nombre} <em>{formato(s.valores[hover])}</em></span>)}
      </div>}
      <div className="leyenda">
        {series.map((s) => <span key={s.nombre}><i style={{ background: s.color }} />{s.nombre}</span>)}
        {marcas.length > 0 && <><span><i className="tri compra" />Compra</span><span><i className="tri venta" />Venta</span></>}
      </div>
    </div>
  );
}
