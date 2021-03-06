from __future__ import absolute_import, division

import logging
import time
from builtins import int

import numpy as np
from future.utils import raise_with_traceback
from scipy.stats import ks_2samp
from sklearn.metrics import silhouette_score

from .mediods import k_medoids
from .tfidf import get_n_top_keywords
from .utils import split_to_chunks
from .word2vec import text2ids, train_word2vec

DEFAULT_T = 10
DEFAULT_CHUNK_SIZE = 50
DEFAULT_N_TOP_KEYWORDS = 1000

DEFAULT_CLUSTERING_K = 2
DEFAULT_CLUSTERING_SPAWN = 10


def _calculate_similarity_matrix(model, words, chunk_size=DEFAULT_CHUNK_SIZE):
    chunks = split_to_chunks(words, chunk_size)

    logging.debug("No. of words: {}, Chunk size: {}".format(
        len(words), chunk_size))

    chunks_num = int(
        len(words) / chunk_size) + (1 if (len(words) % chunk_size != 0) else 0)

    logging.debug("No. of chunks {}".format(chunks_num))

    similarites_vector_size = (chunk_size * (chunk_size - 1)) // 2
    similarites_matrix = np.zeros((chunks_num, similarites_vector_size))

    similarity_func = np.vectorize(
        lambda x, y: model.similarity(x, y), otypes=[float])

    chunk_index = 0
    for chunk in chunks:
        in_chunk_index = 0
        for i in range(len(chunk)):
            similarities = similarity_func(chunk[i], chunk[i + 1:len(chunk)])
            similarites_matrix[chunk_index, in_chunk_index:in_chunk_index +
                               len(similarities)] = similarities
            in_chunk_index += len(similarities)

        chunk_index += 1

    logging.debug("Similarity matrix shape {}".format(
        similarites_matrix.shape))

    return similarites_matrix


def _calculate_zv(first_mat, i, second_mat, j, T=DEFAULT_T):
    ks = np.apply_along_axis(
        ks_2samp,
        1,
        second_mat[j - T + 1:j],
        first_mat[i],
    )
    ks_stats = ks[:, 0]

    return np.average(ks_stats)


def _calculate_zv_distances(similarites_matrix, T=DEFAULT_T):
    chunks_num = similarites_matrix.shape[0]

    if chunks_num < T:
        err_msg = "The are to few chunks for calculate ZV distance, chunks number:{} must be bigger the T:{}.".format(
            chunks_num, T)
        logging.error(err_msg)
        raise_with_traceback(Exception(err_msg))

    ZVs = np.zeros(chunks_num - T - 1)

    for i in range(ZVs.shape[0]):
        ZVs[i] = _calculate_zv(similarites_matrix, T + i, similarites_matrix,
                               T + i - 1, T)

    return ZVs


def _calculate_dzv_distances(first_similarites_matrix,
                             second_similarites_matrix,
                             T=DEFAULT_T):

    DZV = np.zeros((first_similarites_matrix.shape[0] - T - 1,
                    second_similarites_matrix.shape[0] - T - 1))

    for i in range(DZV.shape[0]):
        zv_1 = _calculate_zv(first_similarites_matrix, T + i,
                             first_similarites_matrix, T + i - 1, T)

        for j in range(DZV.shape[1]):
            zv_2 = _calculate_zv(second_similarites_matrix, T + j,
                                 second_similarites_matrix, T + j - 1, T)
            zv_3 = _calculate_zv(first_similarites_matrix, T + i,
                                 second_similarites_matrix, T + j - 1, T)
            zv_4 = _calculate_zv(second_similarites_matrix, T + j,
                                 first_similarites_matrix, T + i - 1, T)
            DZV[i, j] = abs(zv_1 + zv_2 - zv_3 - zv_4)

    return DZV


def zv_process(text,
               model,
               stop_words,
               keywords,
               T=DEFAULT_T,
               chunk_size=DEFAULT_CHUNK_SIZE):

    start_time = time.time()
    ids, words = text2ids(
        model=model,
        text=text,
        stop_words=stop_words,
        acceptable_tokens=keywords,
        remove_skipped_tokens=True)
    end_time = time.time()
    logging.debug("word2vec runs {:.4f} seconds".format(end_time - start_time))

    start_time = time.time()
    sim_mat = _calculate_similarity_matrix(model, words, chunk_size)
    end_time = time.time()
    logging.debug(
        "similarity matrix calculation took {:.4f} seconds".format(end_time -
                                                                   start_time))

    del ids, words

    start_time = time.time()
    ZVs = _calculate_zv_distances(sim_mat, T)
    end_time = time.time()
    logging.debug(
        "ZV distances calculation took {:.4f} seconds".format(end_time -
                                                              start_time))

    del sim_mat

    return ZVs


def dzv_process(first_text,
                second_text,
                model,
                stop_words,
                keywords,
                T=DEFAULT_T,
                chunk_size=DEFAULT_CHUNK_SIZE):

    start_time = time.time()
    first_text_ids, first_text_words = text2ids(
        model=model,
        text=first_text,
        stop_words=stop_words,
        acceptable_tokens=keywords,
        remove_skipped_tokens=True)
    end_time = time.time()
    logging.debug("first text word2vec runs {:.4f} seconds".format(end_time -
                                                                   start_time))

    start_time = time.time()
    first_sim_mat = _calculate_similarity_matrix(model, first_text_words,
                                                 chunk_size)
    end_time = time.time()
    logging.debug(
        "first text similarity matrix calculation took {:.4f} seconds".format(
            end_time - start_time))

    del first_text_ids, first_text_words

    start_time = time.time()
    second_text_ids, second_text_words = text2ids(
        model=model,
        text=second_text,
        stop_words=stop_words,
        acceptable_tokens=keywords,
        remove_skipped_tokens=True)
    end_time = time.time()
    logging.debug(
        "second text word2vec runs {:.4f} seconds".format(end_time -
                                                          start_time))

    start_time = time.time()
    second_sim_mat = _calculate_similarity_matrix(model, second_text_words,
                                                  chunk_size)
    end_time = time.time()
    logging.debug(
        "second text similarity matrix calculation took {:.4f} seconds".format(
            end_time - start_time))

    del second_text_ids, second_text_words

    start_time = time.time()
    DZV = _calculate_dzv_distances(
        first_similarites_matrix=first_sim_mat,
        second_similarites_matrix=second_sim_mat,
        T=T)

    end_time = time.time()
    logging.debug(
        "DZV matrix calculation took {:.4f} seconds".format(end_time -
                                                            start_time))

    del first_sim_mat, second_sim_mat

    return DZV


def _preprocess(texts, model=None, n_top_keywords=DEFAULT_N_TOP_KEYWORDS):

    stop_words = []

    if model is None:
        model = train_word2vec(texts, stop_words, iter=20)

    keywords = get_n_top_keywords(texts, stop_words, int(n_top_keywords * 1.5))
    n_top_keyword = [
        keyword[0] for keyword in keywords if keyword[0] in model.wv.vocab
    ]
    n_top_keyword = n_top_keyword[:min(len(n_top_keyword), n_top_keywords)]

    return stop_words, model, n_top_keyword


def execute_algorithm(first_text,
                      second_text,
                      model=None,
                      T=DEFAULT_T,
                      chunk_size=DEFAULT_CHUNK_SIZE,
                      n_top_keywords=DEFAULT_N_TOP_KEYWORDS):

    del_model = model is None

    start_time = time.time()
    stop_words, model, n_top_keyword = _preprocess(
        texts=[first_text, second_text],
        model=model,
        n_top_keywords=n_top_keywords)
    end_time = time.time()
    logging.debug(
        "Preprocessing took {:.4f} seconds".format(end_time - start_time))

    start_time = time.time()
    ZV = zv_process(
        text=first_text + " " + second_text,
        model=model,
        stop_words=stop_words,
        keywords=n_top_keyword,
        T=T,
        chunk_size=chunk_size)
    end_time = time.time()
    logging.debug(
        "ZV calculation took {:.4f} seconds".format(end_time - start_time))

    start_time = time.time()
    DZV = dzv_process(
        first_text=first_text,
        second_text=second_text,
        model=model,
        stop_words=stop_words,
        keywords=n_top_keyword,
        T=T,
        chunk_size=chunk_size)
    end_time = time.time()
    logging.debug(
        "DZV calculation took {:.4f} seconds".format(end_time - start_time))

    if del_model:
        del model

    clustering_result = execute_dzv_clustering(DZV)

    return ZV, DZV, clustering_result


def execute_zv(text,
               model=None,
               T=DEFAULT_T,
               chunk_size=DEFAULT_CHUNK_SIZE,
               n_top_keywords=DEFAULT_N_TOP_KEYWORDS):

    del_model = model is None

    start_time = time.time()
    stop_words, model, n_top_keyword = _preprocess(
        texts=[text], model=model, n_top_keywords=n_top_keywords)
    end_time = time.time()
    logging.debug(
        "Preprocessing took {:.4f} seconds".format(end_time - start_time))

    start_time = time.time()
    ZV = zv_process(
        text=text,
        model=model,
        stop_words=stop_words,
        keywords=n_top_keyword,
        T=T,
        chunk_size=chunk_size)
    end_time = time.time()
    logging.debug(
        "ZV calculation took {:.4f} seconds".format(end_time - start_time))

    if del_model:
        del model

    return ZV


def execute_dzv(first_text,
                second_text,
                model=None,
                T=DEFAULT_T,
                chunk_size=DEFAULT_CHUNK_SIZE,
                n_top_keywords=DEFAULT_N_TOP_KEYWORDS):

    del_model = model is None

    start_time = time.time()
    stop_words, model, n_top_keyword = _preprocess(
        texts=[first_text, second_text],
        model=model,
        n_top_keywords=n_top_keywords)
    end_time = time.time()
    logging.debug(
        "Preprocessing took {:.4f} seconds".format(end_time - start_time))

    start_time = time.time()
    DZV = dzv_process(
        first_text=first_text,
        second_text=second_text,
        model=model,
        stop_words=stop_words,
        keywords=n_top_keyword,
        T=T,
        chunk_size=chunk_size)
    end_time = time.time()
    logging.debug(
        "DZV calculation took {:.4f} seconds".format(end_time - start_time))

    if del_model:
        del model

    return DZV


def execute_dzv_clustering(dzv,
                           k=DEFAULT_CLUSTERING_K,
                           spawn=DEFAULT_CLUSTERING_SPAWN):

    if k < 2:
        k = 2
    if spawn < 1:
        spawn = 1

    def distance(a, b):
        return np.linalg.norm(a - b)

    start_time = time.time()

    diameter, medoids = k_medoids(
        k=k,
        points=dzv,
        distance=distance,
        spawn=spawn,
        equality=distance,
        verbose=True)
    end_time = time.time()
    logging.debug(
        "DZV clustering took {:.4f} seconds".format(end_time - start_time))

    logging.debug(
        "Clustering to {} clusters with spawn of {} gives diameter of {:.4f}".
        format(k, spawn, diameter))

    labels = np.zeros(dzv.shape[0], dtype=np.int)
    distances = np.zeros(dzv.shape[0])
    for i, row in enumerate(dzv):
        row_distances = [distance(medoid.kernel, row) for medoid in medoids]
        min_index = np.argmin(row_distances)
        labels[i] = min_index + 1
        distances[i] = row_distances[min_index]

    silhouette = silhouette_score(dzv, labels, distance)
    logging.debug(
        "Clustering to {} clusters gives silhouette score of {:.4f}".format(
            k, silhouette))

    return labels, distances, silhouette
