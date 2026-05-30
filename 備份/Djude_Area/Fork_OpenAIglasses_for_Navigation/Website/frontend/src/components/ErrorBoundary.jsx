/**
 * ErrorBoundary 元件 — 捕獲子元件樹的渲染錯誤
 * 防止 3D 模型載入失敗等意外導致整頁白屏
 */
import { Component } from 'react'
import { Link } from 'react-router-dom'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary 捕獲錯誤：', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-[300px] flex items-center justify-center p-8">
          <div className="text-center max-w-md">
            <div className="text-5xl mb-4">⚠️</div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
              發生錯誤
            </h2>
            <p className="text-gray-700 dark:text-gray-400 text-sm mb-6 leading-relaxed">
              此區塊發生了未預期的錯誤。請嘗試重新整理頁面，若問題持續請聯繫管理員。
            </p>
            <div className="flex flex-wrap gap-3 justify-center">
              <button
                onClick={() => this.setState({ hasError: false, error: null })}
                className="btn-primary text-sm py-2 px-6"
              >
                重試
              </button>
              <Link to="/" className="btn-outline text-sm py-2 px-6">
                返回首頁
              </Link>
            </div>
            {process.env.NODE_ENV === 'development' && this.state.error && (
              <details className="mt-6 text-left">
                <summary className="text-xs text-gray-400 cursor-pointer">錯誤詳情</summary>
                <pre className="mt-2 text-xs text-red-400 bg-red-500/10 rounded-lg p-3 overflow-x-auto">
                  {this.state.error.toString()}
                </pre>
              </details>
            )}
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
