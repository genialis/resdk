"""Column mappings for QC tables.

Column mappings with the GENERAL_ prefix are designated for the general summary table in MultiQC.
In this case, the mappings are not split by file from which the information is extracted
but based on the type of information.

If ''name'' key includes a list,
it means that the column names have changed between MultiQC versions.
Using both names ensures that the correct column is selected regardless
of the MultiQC version used when processing the data.

Key ''scaling_factor'' is used to get values on a common scale.
For example, if the value is provided in millions, the scaling factor is 1e6.
This change in MultiQC generated summary table files was observed when updating
the MultiQC version, where read counts were formatted
in more human readable format (millions) instead of whole numbers.
"""

SAMPLE_INFO_MAP = [
    {
        "name": "Species",
        "slug": "species",
        "type": "string",
        "agg_func": "first",
    },
    {
        "name": "Genome Build",
        "slug": "genome_build",
        "type": "string",
        "agg_func": "first",
    },
]

GENERAL_FASTQ_MAP = [
    {
        "name": [
            "FastQC (raw)_mqc-generalstats-fastqc_raw-total_sequences",
            "fastqc_raw-total_sequences",
        ],
        "slug": "total_read_count_raw",
        "type": "Int64",
        "agg_func": "sum",
        "scaling_factor": {"fastqc_raw-total_sequences": 1e6},
    },
    {
        "name": [
            "FastQC (trimmed)_mqc-generalstats-fastqc_trimmed-total_sequences",
            "fastqc_trimmed-total_sequences",
        ],
        "slug": "total_read_count_trimmed",
        "type": "Int64",
        "agg_func": "sum",
        "scaling_factor": {"fastqc_trimmed-total_sequences": 1e6},
    },
    {
        "name": [
            "FastQC (raw)_mqc-generalstats-fastqc_raw-total_sequences",
            "fastqc_raw-total_sequences",
        ],
        "slug": "estimated_fragment_count_raw",
        "type": "Int64",
        "agg_func": "mean",
        "scaling_factor": {"fastqc_raw-total_sequences": 1e6},
    },
    {
        "name": [
            "FastQC (trimmed)_mqc-generalstats-fastqc_trimmed-total_sequences",
            "fastqc_trimmed-total_sequences",
        ],
        "slug": "estimated_fragment_count_trimmed",
        "type": "Int64",
        "agg_func": "mean",
        "scaling_factor": {"fastqc_trimmed-total_sequences": 1e6},
    },
    {
        "name": [
            "FastQC (raw)_mqc-generalstats-fastqc_raw-percent_gc",
            "fastqc_raw-percent_gc",
        ],
        "slug": "gc_content_raw",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": [
            "FastQC (trimmed)_mqc-generalstats-fastqc_trimmed-percent_gc",
            "fastqc_trimmed-percent_gc",
        ],
        "slug": "gc_content_trimmed",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": [
            "FastQC (raw)_mqc-generalstats-fastqc_raw-percent_duplicates",
            "fastqc_raw-percent_duplicates",
        ],
        "slug": "seq_duplication_raw",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": [
            "FastQC (trimmed)_mqc-generalstats-fastqc_trimmed-percent_duplicates",
            "fastqc_trimmed-percent_duplicates",
        ],
        "slug": "seq_duplication_trimmed",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": [
            "FastQC (raw)_mqc-generalstats-fastqc_raw-avg_sequence_length",
            "fastqc_raw-avg_sequence_length",
        ],
        "slug": "avg_seq_length_raw",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": [
            "FastQC (trimmed)_mqc-generalstats-fastqc_trimmed-avg_sequence_length",
            "fastqc_trimmed-avg_sequence_length",
        ],
        "slug": "avg_seq_length_trimmed",
        "type": "Float64",
        "agg_func": "mean",
    },
]

GENERAL_ALIGNMENT_MAP = [
    {
        "name": [
            "STAR_mqc-generalstats-star-uniquely_mapped_percent",
            "star-uniquely_mapped_percent",
        ],
        "slug": "mapped_reads_percent",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": ["STAR_mqc-generalstats-star-uniquely_mapped", "star-uniquely_mapped"],
        "slug": "mapped_reads",
        "type": "Int64",
        "agg_func": "sum",
        "scaling_factor": {"star-uniquely_mapped": 1e6},
    },
    {
        "name": [
            "STAR (Globin)_mqc-generalstats-star_globin-uniquely_mapped_percent",
            "star_globin-uniquely_mapped_percent",
        ],
        "slug": "mapped_reads_percent_globin",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": [
            "STAR (Globin)_mqc-generalstats-star_globin-uniquely_mapped",
            "star_globin-uniquely_mapped",
        ],
        "slug": "mapped_reads_globin",
        "type": "Int64",
        "agg_func": "sum",
        "scaling_factor": {"star_globin-uniquely_mapped": 1e6},
    },
    {
        "name": [
            "STAR (rRNA)_mqc-generalstats-star_rrna-uniquely_mapped_percent",
            "star_rrna-uniquely_mapped_percent",
        ],
        "slug": "mapped_reads_percent_rRNA",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": [
            "STAR (rRNA)_mqc-generalstats-star_rrna-uniquely_mapped",
            "star_rrna-uniquely_mapped",
        ],
        "slug": "mapped_reads_rRNA",
        "type": "Int64",
        "agg_func": "sum",
        "scaling_factor": {"star_rrna-uniquely_mapped": 1e6},
    },
    {
        "name": [
            "STAR (downsampled)_mqc-generalstats-star_downsampled-uniquely_mapped_percent",
            "star_downsampled-uniquely_mapped_percent",
        ],
        "slug": "mapped_reads_percent_downsampled",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": [
            "STAR (downsampled)_mqc-generalstats-star_downsampled-uniquely_mapped",
            "star_downsampled-uniquely_mapped",
        ],
        "slug": "mapped_reads_downsampled",
        "type": "Int64",
        "agg_func": "sum",
        "scaling_factor": {"star_downsampled-uniquely_mapped": 1e6},
    },
]

GENERAL_QUANTIFICATION_MAP = [
    {
        "name": [
            "featureCounts_mqc-generalstats-featurecounts-percent_assigned",
            "featurecounts-percent_assigned",
        ],
        "slug": "fc_assigned_reads_percent",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": [
            "featureCounts_mqc-generalstats-featurecounts-Assigned",
            "featurecounts-Assigned",
        ],
        "slug": "fc_assigned_reads",
        "type": "Int64",
        "agg_func": "sum",
        "scaling_factor": {"featurecounts-Assigned": 1e6},
    },
    {
        "name": [
            "STAR quantification_mqc-generalstats-star_quantification-of_assigned_reads",
            "custom_content-of_assigned_reads",
        ],
        "slug": "star_assigned_reads_percent",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": [
            "STAR quantification_mqc-generalstats-star_quantification-Assigned_reads",
            "custom_content-Assigned_reads",
        ],
        "slug": "star_assigned_reads",
        "type": "Int64",
        "agg_func": "sum",
    },
    {
        "name": [
            "Salmon_mqc-generalstats-salmon-percent_mapped",
            "salmon-percent_mapped",
        ],
        "slug": "salmon_assigned_reads_percent",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": ["Salmon_mqc-generalstats-salmon-num_mapped", "salmon-num_mapped"],
        "slug": "salmon_assigned_reads",
        "type": "Int64",
        "agg_func": "sum",
        "scaling_factor": {"salmon-num_mapped": 1e6},
    },
]

GENERAL_QC_MAP = [
    {
        "name": [
            "QoRTs_mqc-generalstats-qorts-Genes_PercentWithNonzeroCounts",
            "qorts-Genes_PercentWithNonzeroCounts",
        ],
        "slug": "nonzero_count_features_percent",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": [
            "QoRTs_mqc-generalstats-qorts-NumberOfChromosomesCovered",
            "qorts-NumberOfChromosomesCovered",
        ],
        "slug": "contigs_covered",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "RNA-SeQC_mqc-generalstats-rna_seqc-Expression_Profiling_Efficiency",
        "slug": "profiling_efficiency",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "RNA-SeQC_mqc-generalstats-rna_seqc-Genes_Detected",
        "slug": "genes_detected",
        "type": "Int64",
        "agg_func": "mean",
    },
]

MACS_SUMMARY_MAP = [
    {
        "name": "peak_count",
        "slug": "macs_peak_count",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "fragment_size",
        "slug": "macs_fragment_size",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "treatment_fragments_total",
        "slug": "macs_treatment_fragments_total",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "control_fragments_total",
        "slug": "macs_control_fragments_total",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "d",
        "slug": "macs_fragment_length",
        "type": "Int64",
        "agg_func": "mean",
    },
]

MACS_PREPEAK_MAP = [
    {
        "name": "TOTAL_READS",
        "slug": "prepeak_total_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "MAPPED_READS",
        "slug": "prepeak_mapped_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "MAPPED_PERCENTAGE",
        "slug": "prepeak_mapped_percentage",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "UNPAIRED_READS_EXAMINED",
        "slug": "prepeak_unpaired_reads_examined",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "READ_PAIRS_EXAMINED",
        "slug": "prepeak_read_pairs_examined",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "UNPAIRED_READ_DUPLICATES",
        "slug": "prepeak_unpaired_read_duplicates",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PERCENT_DUPLICATION",
        "slug": "prepeak_percent_duplication",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "NRF",
        "slug": "prepeak_nrf",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PBC1",
        "slug": "prepeak_pbc1",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PBC2",
        "slug": "prepeak_pbc2",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "NSC",
        "slug": "prepeak_nsc",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "RSC",
        "slug": "prepeak_rsc",
        "type": "Float64",
        "agg_func": "mean",
    },
]

MACS_POSTPEAK_MAP = [
    {
        "name": "FRiP",
        "slug": "postpeak_frip",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "NUMBER_OF_PEAKS",
        "slug": "postpeak_number_of_peaks",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "NUMBER_OF_READS_IN_PROMOTERS",
        "slug": "postpeak_number_of_reads_in_promoters",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "FRACTION_OF_READS_IN_PROMOTERS",
        "slug": "postpeak_fraction_of_reads_in_promoters",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "NUMBER_OF_PEAKS_IN_PROMOTERS",
        "slug": "postpeak_number_of_peaks_in_promoters",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "FRACTION_OF_PEAKS_IN_PROMOTERS",
        "slug": "postpeak_fraction_of_peaks_in_promoters",
        "type": "Float64",
        "agg_func": "mean",
    },
]

PICARD_WGS_MAP = [
    {
        "name": "GENOME_TERRITORY",
        "slug": "picard_genome_territory",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "MEAN_COVERAGE",
        "slug": "picard_mean_coverage",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "SD_COVERAGE",
        "slug": "picard_sd_coverage",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "MEDIAN_COVERAGE",
        "slug": "picard_median_coverage",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "MAD_COVERAGE",
        "slug": "picard_mad_coverage",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_EXC_ADAPTER",
        "slug": "picard_pct_exc_adapter",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_EXC_MAPQ",
        "slug": "picard_pct_exc_mapq",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_EXC_DUPE",
        "slug": "picard_pct_exc_dupe",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_EXC_UNPAIRED",
        "slug": "picard_pct_exc_unpaired",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_EXC_BASEQ",
        "slug": "picard_pct_exc_baseq",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_EXC_OVERLAP",
        "slug": "picard_pct_exc_overlap",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_EXC_CAPPED",
        "slug": "picard_pct_exc_capped",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_EXC_TOTAL",
        "slug": "picard_pct_exc_total",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "HET_SNP_SENSITIVITY",
        "slug": "picard_het_snp_sensitivity",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "HET_SNP_Q",
        "slug": "picard_het_snp_q",
        "type": "Float64",
        "agg_func": "mean",
    },
]

PICARD_ALIGNMENT_MAP = [
    {
        "name": "TOTAL_READS",
        "slug": "picard_total_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PF_READS",
        "slug": "picard_pf_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_PF_READS",
        "slug": "picard_pct_pf_reads",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PF_NOISE_READS",
        "slug": "picard_pf_noise_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PF_READS_ALIGNED",
        "slug": "picard_pf_reads_aligned",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_PF_READS_ALIGNED",
        "slug": "picard_pct_pf_reads_aligned",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PF_ALIGNED_BASES",
        "slug": "picard_pf_aligned_bases",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PF_HQ_ALIGNED_READS",
        "slug": "picard_pf_hq_aligned_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PF_HQ_ALIGNED_BASES",
        "slug": "picard_pf_hq_aligned_bases",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PF_HQ_ALIGNED_Q20_BASES",
        "slug": "picard_pf_hq_aligned_q20_bases",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PF_MISMATCH_RATE",
        "slug": "picard_pf_mismatch_rate",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PF_HQ_ERROR_RATE",
        "slug": "picard_pf_hq_error_rate",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PF_INDEL_RATE",
        "slug": "picard_pf_indel_rate",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "MEAN_READ_LENGTH",
        "slug": "picard_mean_read_length",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "READS_ALIGNED_IN_PAIRS",
        "slug": "picard_reads_aligned_in_pairs",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_READS_ALIGNED_IN_PAIRS",
        "slug": "picard_pct_reads_aligned_in_pairs",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PF_READS_IMPROPER_PAIRS",
        "slug": "picard_pf_reads_improper_pairs",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_PF_READS_IMPROPER_PAIRS",
        "slug": "picard_pct_pf_reads_improper_pairs",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "BAD_CYCLES",
        "slug": "picard_bad_cycles",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "STRAND_BALANCE",
        "slug": "picard_strand_balance",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_CHIMERAS",
        "slug": "picard_pct_chimeras",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_ADAPTER",
        "slug": "picard_pct_adapter",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_SOFTCLIP",
        "slug": "picard_pct_softclip",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_HARDCLIP",
        "slug": "picard_pct_hardclip",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "AVG_POS_3PRIME_SOFTCLIP_LENGTH",
        "slug": "picard_avg_pos_3prime_softclip_length",
        "type": "Float64",
        "agg_func": "mean",
    },
]

PICARD_DUPS_MAP = [
    {
        "name": "UNPAIRED_READS_EXAMINED",
        "slug": "picard_unpaired_reads_examined",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "READ_PAIRS_EXAMINED",
        "slug": "picard_read_pairs_examined",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SECONDARY_OR_SUPPLEMENTARY_RDS",
        "slug": "picard_secondary_or_supplementary_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "UNMAPPED_READS",
        "slug": "picard_unmapped_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "UNPAIRED_READ_DUPLICATES",
        "slug": "picard_unpaired_read_duplicates",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "READ_PAIR_DUPLICATES",
        "slug": "picard_read_pair_duplicates",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "READ_PAIR_OPTICAL_DUPLICATES",
        "slug": "picard_read_pair_optical_duplicates",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PERCENT_DUPLICATION",
        "slug": "picard_percent_duplication",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "ESTIMATED_LIBRARY_SIZE",
        "slug": "picard_estimated_library_size",
        "type": "Int64",
        "agg_func": "mean",
    },
]

PICARD_INSERT_SIZE_MAP = [
    {
        "name": "MEDIAN_INSERT_SIZE",
        "slug": "picard_insert_median_size",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "MODE_INSERT_SIZE",
        "slug": "picard_insert_mode_size",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "MEDIAN_ABSOLUTE_DEVIATION",
        "slug": "picard_insert_mad",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "MIN_INSERT_SIZE",
        "slug": "picard_insert_min_size",
        "type": "Float64",
        "agg_func": "min",
    },
    {
        "name": "MAX_INSERT_SIZE",
        "slug": "picard_insert_max_size",
        "type": "Float64",
        "agg_func": "max",
    },
    {
        "name": "MEAN_INSERT_SIZE",
        "slug": "picard_insert_mean_size",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "STANDARD_DEVIATION",
        "slug": "picard_insert_std_dev",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "READ_PAIRS",
        "slug": "picard_insert_read_pairs",
        "type": "Int64",
        "agg_func": "sum",
    },
    {
        "name": "PAIR_ORIENTATION",
        "slug": "picard_insert_pair_orientation",
        "type": "string",
        "agg_func": "first",
    },
]

PICARD_METHYLATION_MAP = [
    {
        "name": "NON_CPG_BASES",
        "slug": "picard_non_cpg_bases",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "NON_CPG_CONVERTED_BASES",
        "slug": "picard_non_cpg_converted_bases",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_NON_CPG_BASES_CONVERTED",
        "slug": "picard_pct_non_cpg_bases_converted",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "CPG_BASES_SEEN",
        "slug": "picard_cpg_bases_seen",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "CPG_BASES_CONVERTED",
        "slug": "picard_cpg_bases_converted",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "PCT_CPG_BASES_CONVERTED",
        "slug": "picard_pct_cpg_bases_converted",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "MEAN_CPG_COVERAGE",
        "slug": "picard_mean_cpg_coverage",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "MEDIAN_CPG_COVERAGE",
        "slug": "picard_median_cpg_coverage",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "READS_WITH_NO_CPG",
        "slug": "picard_reads_with_no_cpg",
        "type": "Int64",
        "agg_func": "mean",
    },
]

QORTS_SUMMARY_MAP = [
    {"name": "Genes_Total", "slug": "genes_total", "type": "Int64", "agg_func": "mean"},
    {
        "name": "Genes_WithZeroCounts",
        "slug": "genes_with_zero_counts",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "Genes_WithNonzeroCounts",
        "slug": "genes_with_nonzero_counts",
        "type": "Int64",
        "agg_func": "mean",
    },
    {"name": "AVG_GC", "slug": "avg_gc", "type": "Float64", "agg_func": "mean"},
    {
        "name": "AggregateGenes",
        "slug": "aggregate_genes",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "AggregateGenes_NoReads",
        "slug": "aggregate_genes_no_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "AggregateGenes_WithReads",
        "slug": "aggregate_genes_with_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {"name": "SpliceLoci", "slug": "splice_loci", "type": "Int64", "agg_func": "mean"},
    {
        "name": "SpliceLoci_Known",
        "slug": "splice_loci_known",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceLoci_Known_NoReads",
        "slug": "splice_loci_known_no_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceLoci_Known_FewReads",
        "slug": "splice_loci_known_few_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceLoci_Known_ManyReads",
        "slug": "splice_loci_known_many_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceLoci_Novel",
        "slug": "splice_loci_novel",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceLoci_Novel_FewReads",
        "slug": "splice_loci_novel_few_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceLoci_Novel_ManyReads",
        "slug": "splice_loci_novel_many_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceEvents",
        "slug": "splice_events",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceEvents_KnownLoci",
        "slug": "splice_events_known_loci",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceEvents_KnownLociWithFewReads",
        "slug": "splice_events_known_loci_few_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceEvents_KnownLociWithManyReads",
        "slug": "splice_events_known_loci_many_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceEvents_NovelLoci",
        "slug": "splice_events_novel_loci",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceEvents_NovelLociWithFewReads",
        "slug": "splice_events_novel_loci_few_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "SpliceEvents_NovelLociWithManyReads",
        "slug": "splice_events_novel_loci_many_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "deletionLoci",
        "slug": "deletion_loci",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "insertionLoci",
        "slug": "insertion_loci",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "deletionEventCt",
        "slug": "deletion_event_count",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "insertionEventCt",
        "slug": "insertion_event_count",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "highCoverageDeletionLoci",
        "slug": "high_coverage_deletion_loci",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "highCoverageInsertionLoci",
        "slug": "high_coverage_insertion_loci",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "StrandTest_frFirstStrand",
        "slug": "first_strand",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "StrandTest_frSecondStrand",
        "slug": "second_strand",
        "type": "Float64",
        "agg_func": "mean",
    },
]

BOWTIE2_MAP = [
    {
        "name": "total_reads",
        "slug": "bowtie_total_reads",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "paired_total",
        "slug": "bowtie_paired_total",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "paired_aligned_none",
        "slug": "bowtie_paired_aligned_none",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "paired_aligned_one",
        "slug": "bowtie_paired_aligned_one",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "paired_aligned_multi",
        "slug": "bowtie_paired_aligned_multi",
        "type": "Int64",
        "agg_func": "mean",
    },
    {
        "name": "overall_alignment_rate",
        "slug": "bowtie_overall_alignment_rate",
        "type": "Float64",
        "agg_func": "mean",
    },
    {
        "name": "paired_aligned_mate_none_halved",
        "slug": "bowtie_paired_aligned_mate_none_halved",
        "type": "Int64",
        "agg_func": "mean",
    },
]
