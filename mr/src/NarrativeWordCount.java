package org.example;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;

import java.io.IOException;
import java.io.StringReader;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class NarrativeWordCount {

    private static final Set<String> STOP_WORDS = new HashSet<>(Arrays.asList(
            // 人称代词、基础虚词
            "i", "me", "my", "myself", "we", "our", "ours", "ourselves",
            "you", "your", "yours", "yourself", "yourselves", "he", "him",
            "his", "himself", "she", "her", "hers", "herself", "it", "its",
            "itself", "they", "them", "their", "theirs", "themselves", "what",
            "which", "who", "whom", "this", "that", "these", "those", "am",
            "is", "are", "was", "were", "be", "been", "being", "have", "has",
            "had", "having", "do", "does", "did", "doing", "a", "an", "the",
            "and", "but", "if", "or", "because", "as", "until", "while", "of",
            "at", "by", "for", "with", "about", "between", "into", "through",
            "during", "before", "after", "above", "below", "to", "from", "up",
            "down", "in", "out", "on", "off", "over", "under", "again", "further",
            "then", "once", "here", "there", "when", "where", "why", "how", "all",
            "any", "both", "each", "few", "more", "most", "other", "some", "such",
            "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
            "s", "t", "can", "will", "just", "don", "should", "now", "would",
            "could", "shouldn", "wasn", "weren", "haven", "hasn", "hadn", "didn",
            "doesn", "isn", "aren", "ain",
            // 隐私脱敏占位符
            "x", "xx", "xxx", "xxxx", "xxxxx", "xxxxxx", "xxxxxxx", "xxxxxxxx",
            // 法律文书通用虚词（无业务痛点价值）
            "act", "section", "date", "fair", "us", "code", "federal", "state",
            "company", "said", "told", "called", "sent", "received", "asked"
    ));


    public static class WordMapper
            extends Mapper<LongWritable, Text, Text, LongWritable> {

        private final Text outKey = new Text();
        private final LongWritable outValue = new LongWritable(1);

        @Override
        protected void map(LongWritable key,
                           Text value,
                           Context context)
                throws IOException, InterruptedException {

            String line = value.toString();

            // 跳过表头
            if (line.startsWith("Date received,")) {
                return;
            }

            try (CSVParser parser = CSVParser.parse(
                    new StringReader(line),
                    CSVFormat.DEFAULT)) {

                for (CSVRecord record : parser) {
                    // 第5列是 Consumer complaint narrative
                    if (record.size() < 6) {
                        context.getCounter("WordCount", "INVALID_CSV").increment(1);
                        return;
                    }

                    String narrative = record.get(5).trim();

                    // 空文本跳过并计数
                    if (narrative.isEmpty()) {
                        context.getCounter("WordCount", "EMPTY_NARRATIVE").increment(1);
                        return;
                    }

                    // 文本清洗：转小写，只保留字母，其余替换为空格
                    String cleanText = narrative.toLowerCase().replaceAll("[^a-z]", " ");
                    // 按空白分割单词
                    String[] words = cleanText.split("\\s+");

                    for (String word : words) {
                        // 过滤：停用词、长度小于3的短词
                        if (word.length() >= 3 && !STOP_WORDS.contains(word)) {
                            outKey.set(word);
                            context.write(outKey, outValue);
                        }
                    }
                }

            } catch (Exception e) {
                context.getCounter("WordCount", "PARSE_ERROR").increment(1);
            }
        }
    }

    public static class WordSumReducer
            extends Reducer<Text, LongWritable, Text, LongWritable> {

        private final LongWritable result = new LongWritable();

        @Override
        protected void reduce(Text key,
                              Iterable<LongWritable> values,
                              Context context)
                throws IOException, InterruptedException {

            long sum = 0;
            for (LongWritable value : values) {
                sum += value.get();
            }

            result.set(sum);
            context.write(key, result);
        }
    }

    public static void main(String[] args) throws Exception {

        if (args.length != 2) {
            System.err.println("用法：NarrativeWordCount <输入路径> <输出路径>");
            System.exit(2);
        }

        Configuration conf = new Configuration();

        Job job = Job.getInstance(conf, "CFPB Complaint Narrative Word Frequency");
        job.setJarByClass(NarrativeWordCount.class);

        job.setMapperClass(WordMapper.class);
        job.setCombinerClass(WordSumReducer.class);
        job.setReducerClass(WordSumReducer.class);

        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(LongWritable.class);

        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(LongWritable.class);

        // 建议设置2个Reduce，提升全量数据运行速度
        job.setNumReduceTasks(2);

        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));

        System.exit(job.waitForCompletion(true) ? 0 : 1);
    }
}
