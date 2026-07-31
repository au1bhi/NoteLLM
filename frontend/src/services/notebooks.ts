import {
  type Body_notebooks_upload_source,
  type NotebookCreate,
  type NotebookPublic,
  type NotebooksPublic,
  NotebooksService,
  type NotebookUpdate,
  type SourcePublic,
  type SourcesPublic,
} from "@/client"

export type Notebook = NotebookPublic
export type NotebooksResponse = NotebooksPublic
export type Source = SourcePublic
export type SourcesResponse = SourcesPublic

export const notebooksApi = {
  create: (input: NotebookCreate) =>
    NotebooksService.createNotebook({ requestBody: input }),
  delete: (notebookId: string) =>
    NotebooksService.deleteNotebook({ notebookId }),
  deleteSource: (notebookId: string, sourceId: string) =>
    NotebooksService.removeSource({ notebookId, sourceId }),
  generateStudyGuide: (notebookId: string) =>
    NotebooksService.generateNotebookStudyGuide({ notebookId }),
  get: (notebookId: string) => NotebooksService.readNotebook({ notebookId }),
  getOverview: (notebookId: string) =>
    NotebooksService.readNotebookOverview({ notebookId }),
  list: () => NotebooksService.readNotebooks(),
  listSources: (notebookId: string) =>
    NotebooksService.readSources({ notebookId }),
  regenerateOverview: (notebookId: string) =>
    NotebooksService.regenerateNotebookOverview({ notebookId }),
  retrySource: (notebookId: string, sourceId: string) =>
    NotebooksService.retrySource({ notebookId, sourceId }),
  search: (notebookId: string, query: string) =>
    NotebooksService.searchNotebook({
      notebookId,
      requestBody: { query },
    }),
  update: (notebookId: string, input: NotebookUpdate) =>
    NotebooksService.updateNotebook({ notebookId, requestBody: input }),
  uploadSource: (notebookId: string, file: File) =>
    NotebooksService.uploadSource({
      notebookId,
      // The generated OpenAPI schema represents a binary multipart field as a
      // string, while the browser client correctly serializes File as FormData.
      formData: { file } as unknown as Body_notebooks_upload_source,
    }),
}
