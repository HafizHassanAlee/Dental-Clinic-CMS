import React, { useEffect, useState } from 'react';
import { DentalChart } from './components/DentalChart';
import { rumiApi } from './services/api';
import type { DentalService, ToothChartEntry } from './types';

export const App: React.FC = () => {
  const [services, setServices] = useState<DentalService[]>([]);
  const [sampleTeeth] = useState<ToothChartEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    rumiApi
      .listServices()
      .then(setServices)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="min-h-screen flex flex-col bg-[#f6f9f9] text-[#07263b]">
      <header className="bg-[#01578c] text-white py-4 px-6 shadow-md">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight">Rumi Dental Care</h1>
            <p className="text-xs text-[#29d8db]">
              Dr. Aisha Salman • 388 A, Block A, RECHS, Johar Town, Lahore • +92 310 2468080
            </p>
          </div>
          <nav className="flex items-center gap-3 text-sm">
            <a href="/services" className="hover:text-[#29d8db]">Services</a>
            <a href="/login" className="px-3 py-1.5 rounded-lg bg-white text-[#01578c] font-semibold">
              Patient Login
            </a>
            <a href="/staff/login" className="px-3 py-1.5 rounded-lg border border-white/40 text-white">
              Staff Login
            </a>
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto w-full p-6 space-y-8 flex-1">
        <section className="bg-white rounded-2xl p-8 border border-slate-200 shadow-sm">
          <span className="inline-block px-3 py-1 rounded-full bg-[#29d8db]/20 text-[#01578c] text-xs font-bold mb-3">
            Mon–Sat: 04:00 PM – 10:00 PM
          </span>
          <h2 className="text-3xl font-extrabold mb-2">
            Trusted Dental Care in Johar Town, Lahore
          </h2>
          <p className="text-slate-600 max-w-2xl mb-6">
            Comprehensive preventive, restorative, endodontic, orthodontic, and implant dentistry
            with strict sterilization and digital patient records.
          </p>
          <div className="flex flex-wrap gap-3">
            <a
              href="/appointment-info"
              className="px-5 py-2.5 rounded-xl bg-[#01578c] text-white font-semibold text-sm"
            >
              Book Appointment
            </a>
            <a
              href="/login"
              className="px-5 py-2.5 rounded-xl border border-[#01578c] text-[#01578c] font-semibold text-sm"
            >
              Access Patient Portal
            </a>
          </div>
        </section>

        {error && (
          <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}

        <section>
          <h3 className="text-xl font-bold mb-4">Clinical Dental Services</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {services.map((svc) => (
              <div
                key={svc.id}
                className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm"
              >
                <div className="text-xs font-bold uppercase text-[#01578c] mb-1">
                  {svc.category}
                </div>
                <h4 className="font-bold text-base mb-2">{svc.name}</h4>
                <p className="text-xs text-slate-600 mb-3">{svc.short_summary}</p>
                <div className="text-xs font-semibold text-slate-500">
                  {svc.price_note}
                </div>
              </div>
            ))}
          </div>
        </section>

        {sampleTeeth.length > 0 && <DentalChart teeth={sampleTeeth} />}
      </main>
    </div>
  );
};
export default App;
