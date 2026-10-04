import { useEffect, useRef, useState } from "react";
import type { Audience } from "../audience";
import { api } from "../api";
import type { PlantRegistration, PlantType } from "../contracts";
import { PlantCharacter } from "./PlantCharacter";

const TYPES: { value: PlantType; emoji: string; label: string; hint: string; color: string }[] = [
  { value: "succulent", emoji: "🌵", label: "Succulent", hint: "cactus, aloe", color: "bg-yellow" },
  { value: "plant", emoji: "🪴", label: "Houseplant", hint: "pothos, fern", color: "bg-green" },
  { value: "tree", emoji: "🌳", label: "Tree", hint: "bonsai, fig", color: "bg-blue" },
];

/** First launch: who you are, what your plant is called, and where it lives. */
export function SignUp({ onDone, audience, onAudience }: { onDone: () => void; audience: Audience; onAudience: (value: Audience) => void }) {
  const [form, setForm] = useState<PlantRegistration>({ username: "", plant_name: "", plant_type: "plant", location: "" });
  const [step, setStep] = useState(0);
  const formRef = useRef<HTMLFormElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [locating, setLocating] = useState(false);
  useEffect(() => { formRef.current?.querySelector<HTMLInputElement>("input")?.focus(); }, [step]);
  const set = (field: keyof PlantRegistration) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [field]: e.target.value });

  const useMyLocation = () => {
    if (!navigator.geolocation) return setError("This browser can't share its location. Type your ZIP code instead.");
    setLocating(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        try {
          const { zip } = await api<{ zip: string }>(`/api/location/zip?lat=${coords.latitude}&lon=${coords.longitude}`);
          setForm((current) => ({ ...current, location: zip }));
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setLocating(false);
        }
      },
      () => {
        setLocating(false);
        setError("Location is turned off. Type your ZIP code instead.");
      },
      { timeout: 10000, maximumAge: 600000 },
    );
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving || locating) return;
    if (step < 2) { setError(null); setStep(step + 1); return; }
    setSaving(true);
    setError(null);
    try {
      await api("/api/plant", { method: "POST", body: JSON.stringify(form) });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="signup-page onboarding">
      <aside className="welcome-garden"><span className="eyebrow">A FRIENDSHIP THAT GROWS</span><h1>A little plant.<br />Your next big adventure.</h1><p>Give your plant a name, listen to its world, and watch your care make a difference.</p><PlantCharacter face="happy" speaking={false} level={0} /><span className="welcome-caption">Your garden starts with hello.</span></aside>
      <form ref={formRef} className="card signup" onSubmit={submit}>
        <div className="setup-progress" aria-label={`Step ${step + 1} of 3`}>{["You", "Your plant", "Your garden"].map((label, index) => <span key={label} className={index === step ? "current" : index < step ? "complete" : ""}>{index+1} · {label}</span>)}</div>
        <span className="eyebrow">STEP {step + 1} OF 3</span>
        <h2>{["First, what should we call you?", "Meet your new growing friend.", "Find your little corner of nature."][step]}</h2>
        <p className="setup-description">{["Pick a nickname for your garden club.", "Every plant has a personality. Give yours a name.", "Your US ZIP code helps us find outdoor air quality."][step]}</p>
        {step === 0 && <>
        <label className="field">
          <span>What's your name?</span>
          <input value={form.username} onChange={set("username")} placeholder="Your nickname" required autoFocus
            pattern="[A-Za-z0-9_.\-]{2,32}" title="2–32 letters or numbers, no spaces" />
          <small>2–32 letters or numbers. No spaces needed.</small>
        </label>

        <label className="field"><span>How much would you like to discover?</span><select value={audience} onChange={e => onAudience(e.target.value as Audience)}><option value="5-7">Ages 5–7 · Simple words</option><option value="8-11">Ages 8–11 · Numbers and explanations</option><option value="12-15">Ages 12–15 · More science</option></select><small>You can change this in your garden. Saved on this browser.</small></label>
        </>}
        {step === 1 && <>
        <label className="field">
          <span>What will you call your plant?</span>
          <input value={form.plant_name} onChange={set("plant_name")} placeholder="Captain Leafy" required maxLength={40} />
        </label>

        <fieldset className="field">
          <legend>What kind of plant is it?</legend>
          <div className="type-choices">
            {TYPES.map((type) => (
              <button type="button" key={type.value}
                className={`type-choice ${type.color} ${form.plant_type === type.value ? "type-chosen" : ""}`}
                aria-pressed={form.plant_type === type.value}
                onClick={() => setForm({ ...form, plant_type: type.value })}>
                <span className="type-emoji" aria-hidden>{type.emoji}</span>
                <strong>{type.label}</strong>
                <small>{type.hint}</small>
              </button>
            ))}
          </div>
        </fieldset>

        </>}
        {step === 2 && <>
        <label className="field">
          <span>Where does your plant live?</span>
          <div className="zip-row">
            <input value={form.location} onChange={set("location")} placeholder="ZIP code, like 48105" required
              inputMode="numeric" pattern="\d{5}" title="5-digit US ZIP code" />
            <button type="button" className="btn btn-blue" onClick={useMyLocation} disabled={locating}>
              {locating ? "Finding…" : "📍 Use my location"}
            </button>
          </div>
        </label>

        <div className="setup-preview">{form.username} + {form.plant_name}<small>A new friendship, ready to grow.</small></div>
        </>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="setup-actions">{step > 0 && <button type="button" className="setup-back" disabled={saving} onClick={() => { setStep(step - 1); setError(null); }}>Back</button>}<button className="btn btn-green btn-big" disabled={saving || locating}>{saving ? "Creating your garden…" : step < 2 ? "Continue →" : "Meet my plant →"}</button></div>
      </form>
    </main>
  );
}
