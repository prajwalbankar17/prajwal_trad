import { useEffect, useRef } from 'react'
import { createChart } from 'lightweight-charts'

/**
 * Candlestick chart with volume, crosshair, zoom/pan, and optional entry,
 * exit, stop-loss and target markers.
 */
export function CandleChart({ candles, markers = [], levels = [], height = 420 }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current) return undefined

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { color: 'transparent' },
        textColor: '#99a2b3',
        fontSize: 11,
        fontFamily: 'JetBrains Mono, monospace',
      },
      grid: {
        vertLines: { color: '#1e2430' },
        horzLines: { color: '#1e2430' },
      },
      rightPriceScale: { borderColor: '#2a3140' },
      timeScale: { borderColor: '#2a3140', timeVisible: true, secondsVisible: false },
      crosshair: {
        mode: 1,
        vertLine: { color: '#3a4254', labelBackgroundColor: '#2a3140' },
        horzLine: { color: '#3a4254', labelBackgroundColor: '#2a3140' },
      },
    })
    chartRef.current = chart

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#2ebd85',
      downColor: '#f6465d',
      borderUpColor: '#2ebd85',
      borderDownColor: '#f6465d',
      wickUpColor: '#2ebd85',
      wickDownColor: '#f6465d',
    })

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    })

    // lightweight-charts wants seconds since epoch, ascending and unique.
    const toTime = (iso) => Math.floor(new Date(iso).getTime() / 1000)

    candleSeries.setData(
      candles.map((c) => ({
        time: toTime(c.ts),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    )
    volumeSeries.setData(
      candles.map((c) => ({
        time: toTime(c.ts),
        value: c.volume,
        color: c.close >= c.open ? 'rgba(46,189,133,.3)' : 'rgba(246,70,93,.3)',
      })),
    )

    if (markers.length) {
      candleSeries.setMarkers(
        markers.map((m) => ({
          time: toTime(m.ts),
          position: m.position ?? 'belowBar',
          color: m.color ?? '#4c8dff',
          shape: m.shape ?? 'arrowUp',
          text: m.text ?? '',
        })),
      )
    }

    levels.forEach((level) => {
      candleSeries.createPriceLine({
        price: level.price,
        color: level.color ?? '#f0b90b',
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: level.title ?? '',
      })
    })

    chart.timeScale().fitContent()

    const resize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    }
    resize()
    window.addEventListener('resize', resize)

    return () => {
      window.removeEventListener('resize', resize)
      chart.remove()
      chartRef.current = null
    }
  }, [candles, markers, levels, height])

  return <div ref={containerRef} className="w-full" />
}
