interface DropOptions {
  busy: boolean;
  importFiles: (files: File[]) => void;
  highlight: (active: boolean) => void;
}

interface FileDrag {
  dataTransfer: DataTransfer;
  preventDefault: () => void;
}

export function assetDropHandlers({ busy, importFiles, highlight }: DropOptions) {
  return {
    onDragOver(event: FileDrag) {
      if (!event.dataTransfer.types.includes('Files')) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = busy ? 'none' : 'copy';
      highlight(!busy);
    },
    onDragLeave(event: { currentTarget: HTMLElement; relatedTarget: EventTarget | null }) {
      if (event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget)) return;
      highlight(false);
    },
    onDrop(event: FileDrag) {
      if (!event.dataTransfer.types.includes('Files')) return;
      event.preventDefault();
      highlight(false);
      const files = Array.from(event.dataTransfer.files);
      if (!busy && files.length) importFiles(files);
    },
  };
}
