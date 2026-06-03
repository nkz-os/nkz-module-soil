import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useSoilApi } from '../hooks/useSoilApi';

interface PenetrometerReading {
    id?: string;
    depthFrom: number;
    depthTo: number;
    resistance: number;  // MPa
    lat: number;
    lon: number;
}

interface Props {
    parcelId: string;
}

export function PenetrometerForm({ parcelId }: Props) {
    const { t } = useTranslation('soil');
    const api = useSoilApi();
    const [readings, setReadings] = useState<PenetrometerReading[]>([]);
    const [loading, setLoading] = useState(false);
    const [rasterizing, setRasterizing] = useState(false);
    const [rasterUrl, setRasterUrl] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    // Form state
    const [depth, setDepth] = useState('0-30');
    const [resistance, setResistance] = useState('');
    const [lat, setLat] = useState('');
    const [lon, setLon] = useState('');

    const fetchReadings = useCallback(async () => {
        try {
            const data = await api.get<{ points?: Array<Record<string, unknown>> }>(
                `/v1/soil/penetrometer/${parcelId}`
            );
            // Fallback: we don't have a dedicated endpoint yet, so we'll use local state for now
        } catch {
            // OK if endpoint doesn't exist yet
        }
    }, [parcelId, api]);

    useEffect(() => {
        fetchReadings();
    }, [fetchReadings]);

    const useGpsLocation = () => {
        if ('geolocation' in navigator) {
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    setLat(pos.coords.latitude.toFixed(6));
                    setLon(pos.coords.longitude.toFixed(6));
                },
                () => setError(t('penetrometer.gpsError', 'GPS not available')),
                { enableHighAccuracy: true, timeout: 10000 }
            );
        }
    };

    const addReading = async () => {
        const res = parseFloat(resistance);
        if (isNaN(res) || res <= 0) {
            setError(t('penetrometer.invalidResistance', 'Enter a valid resistance (MPa)'));
            return;
        }
        const latVal = parseFloat(lat);
        const lonVal = parseFloat(lon);
        if (isNaN(latVal) || isNaN(lonVal)) {
            setError(t('penetrometer.invalidCoords', 'Enter valid coordinates or use GPS'));
            return;
        }

        setLoading(true);
        setError(null);
        try {
            const [dFrom, dTo] = depth.split('-').map(Number);
            await api.post('/v1/soil/sampling-points', {
                lat: latVal,
                lon: lonVal,
                depth_from: dFrom,
                depth_to: dTo,
                penetration_resistance: res,
            });

            const newReading: PenetrometerReading = {
                depthFrom: dFrom,
                depthTo: dTo,
                resistance: res,
                lat: latVal,
                lon: lonVal,
            };
            setReadings(prev => [...prev, newReading]);
            setResistance('');
        } catch (e: any) {
            setError(e?.message || 'Error saving reading');
        } finally {
            setLoading(false);
        }
    };

    const generateRaster = async () => {
        setRasterizing(true);
        setError(null);
        try {
            const resp = await api.post<{
                url: string;
                samplePoints: number;
                method: string;
            }>(`/v1/soil/parcel/${parcelId}/rasterize?property=penetrationResistance&depth=${depth}&resolution=5`);
            setRasterUrl(resp.url);
        } catch (e: any) {
            setError(e?.message || 'Raster generation failed');
        } finally {
            setRasterizing(false);
        }
    };

    return (
        <div className="space-y-3 text-nkz-xs">
            <h4 className="font-medium text-nkz-sm">📏 {t('penetrometer.title', 'Penetrometer Readings')}</h4>

            {/* Add reading form */}
            <div className="border border-nkz-border rounded-nkz-sm p-2 space-y-2">
                <div className="flex gap-2">
                    <select
                        value={depth}
                        onChange={(e) => setDepth(e.target.value)}
                        className="border-nkz-border rounded-nkz-sm flex-1"
                    >
                        <option value="0-30">0-30 cm</option>
                        <option value="30-60">30-60 cm</option>
                        <option value="60-100">60-100 cm</option>
                    </select>
                    <input
                        type="number"
                        step="0.1"
                        min="0"
                        placeholder="MPa"
                        value={resistance}
                        onChange={(e) => setResistance(e.target.value)}
                        className="border-nkz-border rounded-nkz-sm w-20 text-right"
                        inputMode="decimal"
                    />
                </div>
                <div className="flex gap-2">
                    <input
                        type="number"
                        step="0.0001"
                        placeholder="Lat"
                        value={lat}
                        onChange={(e) => setLat(e.target.value)}
                        className="border-nkz-border rounded-nkz-sm flex-1"
                        inputMode="decimal"
                    />
                    <input
                        type="number"
                        step="0.0001"
                        placeholder="Lon"
                        value={lon}
                        onChange={(e) => setLon(e.target.value)}
                        className="border-nkz-border rounded-nkz-sm flex-1"
                        inputMode="decimal"
                    />
                    <button
                        onClick={useGpsLocation}
                        className="px-2 py-1 border border-nkz-border rounded-nkz-sm text-nkz-primary"
                        title={t('penetrometer.useGps', 'Use GPS')}
                    >
                        📍
                    </button>
                </div>
                <button
                    onClick={addReading}
                    disabled={loading || !resistance}
                    className="w-full py-1 bg-nkz-primary text-white rounded-nkz-sm disabled:opacity-50"
                >
                    {loading ? '...' : t('penetrometer.add', 'Add Reading')}
                </button>
            </div>

            {error && (
                <div className="text-red-600 text-nkz-xs">{error}</div>
            )}

            {/* Existing readings */}
            {readings.length > 0 && (
                <div className="space-y-1">
                    <div className="font-medium">{t('penetrometer.readings', 'Readings')}: {readings.length}</div>
                    <div className="max-h-32 overflow-y-auto space-y-1">
                        {readings.map((r, i) => (
                            <div key={i} className="flex justify-between text-nkz-muted text-nkz-xs border-b border-nkz-border pb-1">
                                <span>#{i + 1} {r.depthFrom}-{r.depthTo}cm</span>
                                <span className="font-medium">{r.resistance} MPa</span>
                                <span>{r.lat.toFixed(4)}, {r.lon.toFixed(4)}</span>
                            </div>
                        ))}
                    </div>

                    {readings.length >= 3 && (
                        <button
                            onClick={generateRaster}
                            disabled={rasterizing}
                            className="w-full py-1 bg-nkz-success text-white rounded-nkz-sm disabled:opacity-50 mt-2"
                        >
                            {rasterizing
                                ? t('penetrometer.generating', 'Generating...')
                                : t('penetrometer.generateMap', 'Generate Compaction Map')}
                        </button>
                    )}
                </div>
            )}

            {rasterUrl && (
                <div className="text-nkz-success text-nkz-xs">
                    ✅ {t('penetrometer.mapReady', 'Map ready!')}{' '}
                    <a href={rasterUrl} target="_blank" rel="noopener" className="underline">
                        {t('penetrometer.viewRaster', 'View raster')}
                    </a>
                </div>
            )}
        </div>
    );
}
