# Galactic
Cleaning and curation tools for massive unstructured text datasets.

To get started, install the package (`pip install galactic-ai`) and import it:
```python
from galactic import GalacticDataset
```

## Loading Data
Galactic can load data from a variety of formats.
- CSV
   - `ds = GalacticDataset.from_csv("path/to/file.csv")`
- JSONL
   - `ds = GalacticDataset.from_jsonl("path/to/file.jsonl")`
- 

### Preprocessing
- Trim whitespace
   - `ds.trim_whitespace(fields=["field1", "field2"])`
- Tag text on string
   - `ds.tag_string(fields=["field1"], values=["value1", "value2"], tag="desired_tag")`
- Tag text with RegEx
   - `ds.tag_regex(fields=["field1"], regex="some_regex", tag="desired_tag")`
- Filter on string
   - `ds.filter_string(fields=["field1"], values=["value1", "value2"])`
- Filter with RegEx
   - `ds.filter_regex(fields=["field1"], regex="some_regex")`

### Exploration
- Count tokens
   - `ds.count_tokens(fields=["text_field"])`
- Detect PII
   - `ds.detect_pii(fields=["name", "description"])`
- Detect the language
   - `ds.detect_language(field="text_field")`

### Manipulation
- Generate embeddings
   - `ds.get_embeddings(field="text_field")`
- Retrieve the nearest neighbors
   - `results = ds.get_nearest_neighbors(query="sample text", k=5)`
- Create clusters
   - `ds.cluster(n_clusters=5, method="kmeans")`
- Remove a cluster
   - `ds.remove_cluster(cluster=3)`
- Semantically Dedeplucate
   - `doc.semdedup(threshold=0.95)`
 
## Example
See `example.ipynb` for an example
