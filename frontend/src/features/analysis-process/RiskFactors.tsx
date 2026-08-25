import styles from "./RiskFactors.module.css";

export function RiskFactors({ increasing, reducing }: { increasing: string[]; reducing: string[] }) {
  return <div className={styles.factors}><section><h4>Riski Artıran Faktörler</h4>{increasing.length ? <ul>{increasing.map((factor) => <li key={factor}>{factor}</li>)}</ul> : <p>Doğrulanmış artırıcı faktör mevcut değil.</p>}</section><section><h4>Riski Azaltan Faktörler</h4>{reducing.length ? <ul>{reducing.map((factor) => <li key={factor}>{factor}</li>)}</ul> : <p>Doğrulanmış azaltıcı faktör mevcut değil.</p>}</section></div>;
}
