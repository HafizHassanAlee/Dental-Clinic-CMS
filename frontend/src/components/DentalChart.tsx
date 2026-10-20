import React, { useState } from 'react';
import type { ToothChartEntry } from '../types';

interface DentalChartProps {
  teeth: ToothChartEntry[];
  editable?: boolean;
  onSelectTooth?: (tooth: ToothChartEntry) => void;
}

const STATUS_COLORS: Record<string, string> = {
  healthy: 'bg-emerald-50 border-emerald-400 text-emerald-900',
  caries: 'bg-red-100 border-red-500 text-red-900',
  filling: 'bg-sky-100 border-sky-500 text-sky-900',
  crown: 'bg-amber-100 border-amber-500 text-amber-900',
  root_canal: 'bg-purple-100 border-purple-500 text-purple-900',
  missing: 'bg-slate-200 border-slate-400 text-slate-500 line-through',
  implant: 'bg-teal-100 border-teal-500 text-teal-900',
};

export const DentalChart: React.FC<DentalChartProps> = ({
  teeth,
  onSelectTooth,
}) => {
  const [dentition, setDentition] = useState<'permanent' | 'primary'>('permanent');
  const filtered = teeth.filter((t) => t.dentition_type === dentition);

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
        <div>
          <h3 className="text-lg font-bold text-[#07263b]">
            Interactive FDI Odontogram
          </h3>
          <p className="text-xs text-slate-500">
            FDI Two-Digit Notation — Permanent (11–48) & Primary/Deciduous (51–85)
          </p>
        </div>
        <div className="inline-flex rounded-xl bg-slate-100 p-1">
          <button
            type="button"
            onClick={() => setDentition('permanent')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
              dentition === 'permanent'
                ? 'bg-[#01578c] text-white'
                : 'text-slate-600'
            }`}
          >
            Permanent (11–48)
          </button>
          <button
            type="button"
            onClick={() => setDentition('primary')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
              dentition === 'primary'
                ? 'bg-[#01578c] text-white'
                : 'text-slate-600'
            }`}
          >
            Primary (51–85)
          </button>
        </div>
      </div>

      <div className="grid grid-cols-4 sm:grid-cols-8 gap-2">
        {filtered.map((tooth) => {
          const colorCls =
            STATUS_COLORS[tooth.condition_status] ||
            'bg-slate-50 border-slate-300 text-slate-800';
          return (
            <button
              key={tooth.tooth_code}
              type="button"
              onClick={() => onSelectTooth?.(tooth)}
              className={`p-2.5 rounded-xl border-2 text-left transition hover:shadow-md ${colorCls}`}
            >
              <div className="text-xs font-extrabold">#{tooth.tooth_code}</div>
              <div className="text-[10px] truncate opacity-80">
                {tooth.tooth_name}
              </div>
              <div className="mt-1 text-[10px] font-semibold uppercase tracking-wide">
                {tooth.condition_status.replace('_', ' ')}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
