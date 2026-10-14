import { useEffect, useId, useRef, type ReactNode } from 'react'

interface ModalProps {
  open: boolean
  title: string
  children: ReactNode
  /** Chamado ao apertar Esc. Sem isso, Esc não fecha. */
  onEscape?: () => void
}

/** Usa o <dialog> nativo: já prende o foco e deixa o resto da página inerte. */
export function Modal({ open, title, children, onEscape }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault()
        onEscape?.()
      }}
    >
      {open && (
        <div className="modal__body">
          <h2 id={titleId} className="modal__title">
            {title}
          </h2>
          {children}
        </div>
      )}
    </dialog>
  )
}
